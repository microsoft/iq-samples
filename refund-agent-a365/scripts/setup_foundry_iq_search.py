#!/usr/bin/env python3
"""
setup_foundry_iq_search.py
==========================

Build the **Foundry IQ** knowledge pipeline on **Azure AI Search** for the Refund Agent
sample — the same "Azure Blob Storage -> Azure AI Search Index -> agent knowledge source"
setup the production agent uses (the ``policies-ks`` / ``procurement-ks`` / ``products-ks``
knowledge sources).

For each knowledge category (``policies``, ``procurements``, ``products``) it:

  1. Uploads the local markdown docs in ``knowledge/<category>/`` to a blob container.
  2. Creates an Azure AI Search **data source** (Azure Blob, scoped to that folder).
  3. Creates a vector + semantic **index** (integrated vectorization,
     ``text-embedding-3-small`` @ 1536 dims, HNSW/cosine + scalar quantization).
  4. Creates a **skillset** (SplitSkill -> AzureOpenAIEmbeddingSkill -> index projections).
  5. Creates and runs an **indexer**.

The resulting indexes are what you attach to the Foundry agent as
"Azure AI Search Index" knowledge sources (Foundry portal -> agent ->
Knowledge and tools -> + Add -> Azure AI Search Index).

This mirrors the production ``refund-agent-blob-ks`` pipeline field-for-field
(fields: ``uid`` [key], ``snippet_parent_id``, ``blob_url``, ``snippet``,
``snippet_vector``; parent/child projections with ``skipIndexingParentDocuments``).

--------------------------------------------------------------------------------
Auth (keyless by default — run ``az login`` first)
--------------------------------------------------------------------------------
Uses ``DefaultAzureCredential``. The signed-in principal needs:
  * **Search Service Contributor** + **Search Index Data Contributor** on the search service
  * **Storage Blob Data Contributor** on the storage account

For embeddings, the **search service's managed identity** needs
**Cognitive Services OpenAI User** on the Azure OpenAI resource — OR pass
``--aoai-key`` (or set ``AZURE_OPENAI_EMBEDDING_KEY``) to embed an API key instead.

--------------------------------------------------------------------------------
Usage
--------------------------------------------------------------------------------
    pip install -r scripts/requirements.txt

    # Preview every Azure object that would be created (no calls to Azure):
    python scripts/setup_foundry_iq_search.py --dry-run \
        --search-endpoint https://<svc>.search.windows.net \
        --storage-account <acct> \
        --aoai-endpoint https://<aoai>.openai.azure.com

    # Build the pipeline for all categories:
    python scripts/setup_foundry_iq_search.py \
        --search-endpoint https://<svc>.search.windows.net \
        --storage-account <acct> \
        --aoai-endpoint https://<aoai>.openai.azure.com

    # Only policies, into an existing container, without re-uploading files:
    python scripts/setup_foundry_iq_search.py --categories policies --no-upload ...

Configuration can also come from ``agent/.env`` (same file the other scripts use):
  AZURE_SEARCH_ENDPOINT, AZURE_STORAGE_ACCOUNT, AZURE_STORAGE_CONTAINER,
  AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_EMBEDDING_DEPLOYMENT, AZURE_OPENAI_EMBEDDING_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional for --dry-run
    load_dotenv = None

# ---------------------------------------------------------------------------
# Paths & env
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SAMPLE_DIR = os.path.dirname(_SCRIPT_DIR)
_KNOWLEDGE_DIR = os.path.join(_SAMPLE_DIR, "knowledge")
_ENV_PATH = os.path.join(_SAMPLE_DIR, "agent", ".env")

if load_dotenv is not None:
    if os.path.exists(_ENV_PATH):
        load_dotenv(_ENV_PATH)
    else:
        _tmpl = os.path.join(_SAMPLE_DIR, "agent", ".env.template")
        if os.path.exists(_tmpl):
            load_dotenv(_tmpl)

# Local folder -> knowledge-source suffix used in the Foundry portal (policies-ks, ...).
CATEGORIES = {
    "policies": "policies-ks",
    "procurements": "procurement-ks",
    "products": "products-ks",
}

EMBEDDING_DIMENSIONS = 1536
SPLIT_PAGE_LENGTH = 2000
SPLIT_PAGE_OVERLAP = 200


# ---------------------------------------------------------------------------
# Definition builders (pure — no Azure calls, safe for --dry-run)
# ---------------------------------------------------------------------------
def _names(category: str) -> dict:
    """Deterministic resource names for a category (mirrors the '<ks>-*' pattern)."""
    base = CATEGORIES[category]
    return {
        "index": f"refund-{category}-index",
        "datasource": f"{base}-datasource",
        "skillset": f"{base}-skillset",
        "indexer": f"{base}-indexer",
        "vector_algo": f"{base}-vector-search-algorithm",
        "vector_profile": f"{base}-vector-search-profile",
        "vectorizer": f"{base}-vectorizer",
        "compression": f"{base}-vector-search-scalar-quantization",
        "semantic": f"{base}-semantic-configuration",
    }


def build_index(category: str, cfg: dict):
    from azure.search.documents.indexes.models import (
        SearchIndex,
        SearchField,
        SearchFieldDataType,
        SimpleField,
        SearchableField,
        VectorSearch,
        HnswAlgorithmConfiguration,
        HnswParameters,
        VectorSearchAlgorithmMetric,
        VectorSearchProfile,
        AzureOpenAIVectorizer,
        AzureOpenAIVectorizerParameters,
        ScalarQuantizationCompression,
        ScalarQuantizationParameters,
        RescoringOptions,
        SemanticConfiguration,
        SemanticSearch,
        SemanticPrioritizedFields,
        SemanticField,
    )

    n = _names(category)
    fields = [
        SimpleField(name="uid", type=SearchFieldDataType.String, key=True),
        SimpleField(name="snippet_parent_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="blob_url", type=SearchFieldDataType.String),
        SearchableField(name="snippet", type=SearchFieldDataType.String),
        SearchField(
            name="snippet_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name=n["vector_profile"],
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name=n["vector_algo"],
                parameters=HnswParameters(
                    metric=VectorSearchAlgorithmMetric.COSINE,
                    m=4,
                    ef_construction=400,
                    ef_search=500,
                ),
            )
        ],
        compressions=[
            ScalarQuantizationCompression(
                compression_name=n["compression"],
                rescoring_options=RescoringOptions(
                    enable_rescoring=True, default_oversampling=4.0
                ),
                parameters=ScalarQuantizationParameters(quantized_data_type="int8"),
            )
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name=n["vectorizer"],
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=cfg["aoai_endpoint"],
                    deployment_name=cfg["embedding_deployment"],
                    model_name=cfg["embedding_deployment"],
                    api_key=cfg.get("aoai_key") or None,
                ),
            )
        ],
        profiles=[
            VectorSearchProfile(
                name=n["vector_profile"],
                algorithm_configuration_name=n["vector_algo"],
                compression_name=n["compression"],
                vectorizer_name=n["vectorizer"],
            )
        ],
    )

    semantic_search = SemanticSearch(
        default_configuration_name=n["semantic"],
        configurations=[
            SemanticConfiguration(
                name=n["semantic"],
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="snippet")]
                ),
            )
        ],
    )

    return SearchIndex(
        name=n["index"],
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


def build_skillset(category: str, cfg: dict):
    from azure.search.documents.indexes.models import (
        SearchIndexerSkillset,
        SplitSkill,
        AzureOpenAIEmbeddingSkill,
        InputFieldMappingEntry,
        OutputFieldMappingEntry,
        SearchIndexerIndexProjection,
        SearchIndexerIndexProjectionSelector,
        SearchIndexerIndexProjectionsParameters,
        IndexProjectionMode,
    )

    n = _names(category)
    split_skill = SplitSkill(
        name="SplitSkill",
        description="Split document content into chunks",
        context="/document",
        default_language_code="en",
        text_split_mode="pages",
        maximum_page_length=SPLIT_PAGE_LENGTH,
        page_overlap_length=SPLIT_PAGE_OVERLAP,
        inputs=[InputFieldMappingEntry(name="text", source="/document/content")],
        outputs=[OutputFieldMappingEntry(name="textItems", target_name="pages")],
    )

    embedding_skill = AzureOpenAIEmbeddingSkill(
        name="AzureOpenAIEmbeddingSkill",
        description="Generate embeddings",
        context="/document/pages/*",
        resource_url=cfg["aoai_endpoint"],
        deployment_name=cfg["embedding_deployment"],
        model_name=cfg["embedding_deployment"],
        dimensions=EMBEDDING_DIMENSIONS,
        api_key=cfg.get("aoai_key") or None,
        inputs=[InputFieldMappingEntry(name="text", source="/document/pages/*")],
        outputs=[OutputFieldMappingEntry(name="embedding", target_name="text_vector")],
    )

    projection = SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=n["index"],
                parent_key_field_name="snippet_parent_id",
                source_context="/document/pages/*",
                mappings=[
                    InputFieldMappingEntry(
                        name="snippet_vector", source="/document/pages/*/text_vector"
                    ),
                    InputFieldMappingEntry(name="snippet", source="/document/pages/*"),
                    InputFieldMappingEntry(name="blob_url", source="/document/blob_url"),
                ],
            )
        ],
        parameters=SearchIndexerIndexProjectionsParameters(
            projection_mode=IndexProjectionMode.SKIP_INDEXING_PARENT_DOCUMENTS
        ),
    )

    return SearchIndexerSkillset(
        name=n["skillset"],
        description=f"Skillset for knowledge source '{CATEGORIES[category]}'",
        skills=[split_skill, embedding_skill],
        index_projection=projection,
    )


def build_datasource(category: str, cfg: dict):
    from azure.search.documents.indexes.models import (
        SearchIndexerDataSourceConnection,
        SearchIndexerDataContainer,
    )

    n = _names(category)
    # Scope the indexer to the category's folder within the shared container.
    container = SearchIndexerDataContainer(name=cfg["container"], query=category)
    return SearchIndexerDataSourceConnection(
        name=n["datasource"],
        type="azureblob",
        connection_string=cfg["storage_connection_string"],
        container=container,
    )


def build_indexer(category: str):
    from azure.search.documents.indexes.models import (
        SearchIndexer,
        FieldMapping,
        IndexingParameters,
        IndexingParametersConfiguration,
    )

    n = _names(category)
    return SearchIndexer(
        name=n["indexer"],
        data_source_name=n["datasource"],
        target_index_name=n["index"],
        skillset_name=n["skillset"],
        field_mappings=[
            FieldMapping(source_field_name="metadata_storage_path", target_field_name="blob_url")
        ],
        parameters=IndexingParameters(
            max_failed_items=-1,
            max_failed_items_per_batch=-1,
            configuration=IndexingParametersConfiguration(
                data_to_extract="contentAndMetadata",
                parsing_mode="default",
                query_timeout=None,
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Azure operations
# ---------------------------------------------------------------------------
def _credential():
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def upload_docs(category: str, cfg: dict) -> int:
    """Upload knowledge/<category>/*.md to <container>/<category>/ in blob storage."""
    from azure.storage.blob import BlobServiceClient

    src_dir = os.path.join(_KNOWLEDGE_DIR, category)
    if not os.path.isdir(src_dir):
        print(f"  WARNING: no local docs at {src_dir}, skipping upload.")
        return 0

    account_url = f"https://{cfg['storage_account']}.blob.core.windows.net"
    svc = BlobServiceClient(account_url=account_url, credential=_credential())
    container = svc.get_container_client(cfg["container"])
    try:
        container.create_container()
        print(f"  Created container '{cfg['container']}'.")
    except Exception:
        pass  # already exists

    count = 0
    for fname in sorted(os.listdir(src_dir)):
        if not fname.lower().endswith((".md", ".pdf", ".txt")):
            continue
        blob_name = f"{category}/{fname}"
        with open(os.path.join(src_dir, fname), "rb") as fh:
            container.upload_blob(name=blob_name, data=fh, overwrite=True)
        count += 1
    print(f"  Uploaded {count} file(s) to {cfg['container']}/{category}/")
    return count


def provision(category: str, cfg: dict):
    from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient

    n = _names(category)
    cred = _credential()
    index_client = SearchIndexClient(endpoint=cfg["search_endpoint"], credential=cred)
    indexer_client = SearchIndexerClient(endpoint=cfg["search_endpoint"], credential=cred)

    print(f"  Creating index '{n['index']}'...")
    index_client.create_or_update_index(build_index(category, cfg))

    print(f"  Creating data source '{n['datasource']}'...")
    indexer_client.create_or_update_data_source_connection(build_datasource(category, cfg))

    print(f"  Creating skillset '{n['skillset']}'...")
    indexer_client.create_or_update_skillset(build_skillset(category, cfg))

    print(f"  Creating + running indexer '{n['indexer']}'...")
    indexer_client.create_or_update_indexer(build_indexer(category))
    indexer_client.run_indexer(n["indexer"])
    print(f"  ✓ '{n['index']}' ready — attach it in Foundry as knowledge source '{CATEGORIES[category]}'.")


# ---------------------------------------------------------------------------
# Dry run (validate every definition without touching Azure)
# ---------------------------------------------------------------------------
def dry_run(category: str, cfg: dict):
    def _dump(label, obj):
        try:
            payload = obj.as_dict()
        except Exception:
            payload = {k: v for k, v in vars(obj).items() if not k.startswith("_")}
        print(f"\n----- {label} -----")
        print(json.dumps(payload, indent=2, default=str)[:4000])

    print(f"\n================ DRY RUN: {category} -> {CATEGORIES[category]} ================")
    _dump("INDEX", build_index(category, cfg))
    _dump("DATA SOURCE", build_datasource(category, cfg))
    _dump("SKILLSET", build_skillset(category, cfg))
    _dump("INDEXER", build_indexer(category))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _resolve_config(args) -> dict:
    search_endpoint = args.search_endpoint or os.getenv("AZURE_SEARCH_ENDPOINT", "")
    storage_account = args.storage_account or os.getenv("AZURE_STORAGE_ACCOUNT", "")
    container = args.container or os.getenv("AZURE_STORAGE_CONTAINER", "refundagentdocs")
    aoai_endpoint = args.aoai_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")
    embedding_deployment = args.embedding_deployment or os.getenv(
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
    )
    aoai_key = args.aoai_key or os.getenv("AZURE_OPENAI_EMBEDDING_KEY", "")

    missing = []
    if not search_endpoint:
        missing.append("--search-endpoint / AZURE_SEARCH_ENDPOINT")
    if not storage_account:
        missing.append("--storage-account / AZURE_STORAGE_ACCOUNT")
    if not aoai_endpoint:
        missing.append("--aoai-endpoint / AZURE_OPENAI_ENDPOINT")
    if missing:
        sys.exit("ERROR: missing required config:\n  - " + "\n  - ".join(missing))

    # Keyless blob connection string used by the indexer's data source
    # (ResourceId form -> the search service's managed identity reads the blob).
    storage_connection_string = (
        args.storage_connection_string
        or os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        or f"ResourceId=/subscriptions/{os.getenv('AZURE_SUBSCRIPTION_ID', '<SUBSCRIPTION_ID>')}"
        f"/resourceGroups/{os.getenv('AZURE_RESOURCE_GROUP', '<RESOURCE_GROUP>')}"
        f"/providers/Microsoft.Storage/storageAccounts/{storage_account};"
    )

    return {
        "search_endpoint": search_endpoint.rstrip("/"),
        "storage_account": storage_account,
        "container": container,
        "storage_connection_string": storage_connection_string,
        "aoai_endpoint": aoai_endpoint.rstrip("/"),
        "embedding_deployment": embedding_deployment,
        "aoai_key": aoai_key,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Build the Foundry IQ knowledge pipeline on Azure AI Search "
        "(blob -> index -> skillset -> indexer) for the Refund Agent sample.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--search-endpoint", help="https://<service>.search.windows.net")
    parser.add_argument("--storage-account", help="Storage account name holding the docs")
    parser.add_argument("--container", help="Blob container (default: refundagentdocs)")
    parser.add_argument("--storage-connection-string", help="Override blob connection string")
    parser.add_argument("--aoai-endpoint", help="https://<resource>.openai.azure.com")
    parser.add_argument(
        "--embedding-deployment",
        help="Azure OpenAI embedding deployment/model (default: text-embedding-3-small)",
    )
    parser.add_argument(
        "--aoai-key",
        help="Azure OpenAI API key for embeddings (omit for keyless / managed identity)",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=list(CATEGORIES),
        default=list(CATEGORIES),
        help="Which knowledge categories to build (default: all)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading local docs; index whatever is already in the container",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print every Azure object that would be created, without calling Azure",
    )
    args = parser.parse_args()

    cfg = _resolve_config(args)

    print(f"Search endpoint : {cfg['search_endpoint']}")
    print(f"Storage         : {cfg['storage_account']}/{cfg['container']}")
    print(f"Embeddings      : {cfg['embedding_deployment']} @ {cfg['aoai_endpoint']}")
    print(f"Categories      : {', '.join(args.categories)}")
    print(f"Auth for embeds : {'API key' if cfg['aoai_key'] else 'managed identity (keyless)'}")

    if args.dry_run:
        for category in args.categories:
            dry_run(category, cfg)
        print("\n✓ Dry run complete — no Azure resources were created.")
        return

    for category in args.categories:
        print(f"\n=== {category} -> {CATEGORIES[category]} ===")
        if not args.no_upload:
            upload_docs(category, cfg)
        provision(category, cfg)

    print("\n✓ Done. In the Foundry portal, open your agent -> Knowledge and tools -> "
          "+ Add -> Azure AI Search Index, and attach each index above.")


if __name__ == "__main__":
    main()
