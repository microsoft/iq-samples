"""
Azure Authentication Module
Provides authentication utilities for Azure AI services.
"""
import os
import logging
from typing import Optional

from azure.identity import AzureCliCredential, InteractiveBrowserCredential, ChainedTokenCredential, ManagedIdentityCredential, DefaultAzureCredential
from azure.core.credentials import TokenCredential
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Cached credential instance (lazy initialization)
_credential: Optional[TokenCredential] = None


def get_azure_credential() -> TokenCredential:
    """
    Get Azure credential with fallback chain suitable for both local dev and Azure.
    Tries: Managed Identity (App Service) → CLI (local dev) → Browser (fallback).
    Returns a cached credential instance on subsequent calls.
    """
    global _credential

    if _credential is None:
        logger.info("Initializing Azure credentials...")
        _credential = ChainedTokenCredential(
            ManagedIdentityCredential(),
            AzureCliCredential(),
            InteractiveBrowserCredential(),
        )
        logger.info("Azure credential chain initialized (ManagedIdentity -> CLI -> Browser)")

    return _credential


def get_token(credential: TokenCredential, scope: str) -> str:
    """Get an access token for the specified scope."""
    logger.info(f"Requesting token for scope: {scope}")
    token = credential.get_token(scope)
    logger.info("Token acquired successfully")
    return token.token


def get_inference_client(credential: Optional[TokenCredential] = None):
    """Get Azure AI Inference ChatCompletionsClient configured for the project."""
    endpoint = os.getenv("AZURE_PROJECT_ENDPOINT")
    if not endpoint:
        raise ValueError(
            "AZURE_PROJECT_ENDPOINT environment variable not set. "
            "Please configure it in your .env file."
        )

    if credential is None:
        credential = get_azure_credential()

    try:
        from azure.ai.inference import ChatCompletionsClient
    except ImportError:
        raise ImportError(
            "azure-ai-inference package required for get_inference_client(). "
            "Install with: pip install azure-ai-inference"
        )
    logger.info(f"Creating ChatCompletionsClient for endpoint: {endpoint}")
    client = ChatCompletionsClient(
        endpoint=endpoint,
        credential=credential,
        credential_scopes=["https://cognitiveservices.azure.com/.default"],
    )
    logger.info("ChatCompletionsClient created successfully")

    return client
