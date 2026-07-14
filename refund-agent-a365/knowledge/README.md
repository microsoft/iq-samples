# Foundry IQ Knowledge Documents

These are the enterprise knowledge documents the agent grounds on via **Foundry IQ**
(retrieval-augmented generation). They are the source files behind the agent's
knowledge sources — refund/return policies, procurement contracts, and product specs.

## Folder → Knowledge source mapping

Each folder is indexed into its own Azure AI Search index and attached to the Foundry
agent as a separate knowledge source:

| Folder | Azure AI Search index | Contents |
|--------|----------------------|----------|
| `policies/` | `policies-ks` | Refund/return, shipping SLA, warranty, privacy, quality, sustainability, code of conduct |
| `procurements/` | `procurement-ks` | Vendor agreements, supplier contracts, logistics, manufacturing standards |
| `products/` | `products-ks` | ZavaCore product specifications and plans |

> The refund agent's policy assessments are driven primarily by
> `policies/refund-and-return-policy.md`.

## How Foundry IQ is set up in this sample

Foundry IQ here uses **Azure Blob Storage → Azure AI Search → agent knowledge source**
(not files uploaded directly to the agent).

### Scripted (recommended)

[`../scripts/setup_foundry_iq_search.py`](../scripts/setup_foundry_iq_search.py) builds
the entire pipeline for every category — it uploads these docs to a blob container and
creates the data source, vector + semantic index, split/embedding skillset (integrated
vectorization with `text-embedding-3-small`), and indexer that back `policies-ks`,
`procurement-ks`, and `products-ks`:

```bash
pip install -r ../scripts/requirements.txt
python ../scripts/setup_foundry_iq_search.py \
    --search-endpoint https://<service>.search.windows.net \
    --storage-account <account> \
    --aoai-endpoint https://<resource>.openai.azure.com
```

Add `--dry-run` to preview every Azure object without creating anything. Then attach each
index in the Foundry portal: agent → **Knowledge and tools → + Add → Azure AI Search
Index**.

### Manual (portal)

1. **Upload** these markdown files to an Azure Blob Storage container (one virtual
   folder per category, matching the layout above).
2. **Create an Azure AI Search index** over the blob container for each category
   (`policies-ks`, `procurement-ks`, `products-ks`).
3. **Attach each index** to the Foundry agent: in the Azure AI Foundry portal, open the
   agent → **Knowledge and tools** → **+ Add** → **Azure AI Search Index** → select the
   index. Give each source a clear **name** and **description** (the description tells the
   agent *when* to use that source).

Once attached, the agent automatically searches these documents when a user asks about
refund policies, shipping timelines, warranties, vendors, or product details.

> **Alternative (simpler) setup:** For a smaller demo you can skip Azure AI Search and
> upload individual files directly as Foundry IQ knowledge (FileSearchTool):
> `python ../scripts/setup_foundry_agent.py --knowledge-files policies/*.md`.
> See the repository README's "Set Up Foundry IQ" section.
