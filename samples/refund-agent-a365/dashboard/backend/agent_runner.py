"""
Fabric Agent Runner
Sends questions to a persistent Foundry agent using the Responses API.

The Responses API (/openai/v1/responses) supports On-Behalf-Of (OBO)
identity passthrough required by Fabric Data Agent tools. The older
threads/runs API does NOT support OBO and fails with
"Failed to retrieve data from conversational data retrieval service".

Uses:
- auth.py's get_azure_credential() for token acquisition
- Direct REST calls to the Foundry Responses API
- Scope: https://ai.azure.com/.default

Requires:
- AZURE_PROJECT_ENDPOINT (with /api/projects/<project> suffix)
- FOUNDRY_AGENT_NAME (name of agent to look up)
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Optional

import requests as http_client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Environment variable names
ENV_PROJECT_ENDPOINT = "AZURE_PROJECT_ENDPOINT"
ENV_AGENT_NAME = "FOUNDRY_AGENT_NAME"

# Defaults
DEFAULT_AGENT_NAME = "Refund-agent"
TOKEN_SCOPE = "https://ai.azure.com/.default"
FOUNDRY_API_VERSION = "2025-11-15-preview"

# Retry configuration
MAX_RETRIES = 3
RETRY_WAIT_BASE = 2  # seconds
REQUEST_TIMEOUT = 120  # seconds — Fabric tool calls can be slow

# Re-discover agent version every 5 minutes so we pick up portal updates
VERSION_REFRESH_SECONDS = 300


class FabricAgentRunner:
    """
    Sends questions to an Azure AI Foundry Agent via the Responses API.

    Lifecycle:
    - initialize(): Validate config and verify connectivity
    - ask(question): Send a question, get structured response
    - cleanup(): Release resources
    """

    def __init__(self):
        self._credential = None
        self._endpoint: Optional[str] = None
        self._agent_name: Optional[str] = None
        self._agent_version: Optional[str] = None
        self._version_refreshed_at: float = 0.0
        self._initialized = False

    @property
    def agent_version(self) -> Optional[str]:
        """The resolved latest agent version."""
        return self._agent_version

    @property
    def is_initialized(self) -> bool:
        return self._initialized and self._endpoint is not None

    def initialize(self) -> None:
        """
        Validate configuration and verify we can get a token.
        Call once at application startup.
        """
        from auth import get_azure_credential

        endpoint = os.getenv(ENV_PROJECT_ENDPOINT, "").strip()
        if not endpoint:
            raise ValueError(
                f"{ENV_PROJECT_ENDPOINT} is not set. "
                "See backend/.env for required values."
            )

        self._agent_name = os.getenv(ENV_AGENT_NAME, DEFAULT_AGENT_NAME).strip()
        self._endpoint = endpoint

        logger.info("Initializing FabricAgentRunner (Responses API)")
        logger.info(f"  Endpoint: {endpoint}")
        logger.info(f"  Agent: {self._agent_name}")

        # Get credential and verify token acquisition
        self._credential = get_azure_credential()
        token = self._credential.get_token(TOKEN_SCOPE)
        if not token.token:
            raise ValueError("Failed to acquire token for scope: " + TOKEN_SCOPE)

        self._initialized = True

        # Resolve the latest agent version for Voice Live
        self._agent_version = self._fetch_latest_agent_version()
        self._version_refreshed_at = time.time()
        if self._agent_version:
            logger.info(f"Resolved latest agent version: {self._agent_version}")
        else:
            self._agent_version = os.getenv("FOUNDRY_AGENT_VERSION", "1")
            logger.info(f"Using env agent version: {self._agent_version}")

        logger.info(f"Ready — using agent '{self._agent_name}' v{self._agent_version} via Responses API")

    def _get_token(self) -> str:
        """Get a fresh access token."""
        return self._credential.get_token(TOKEN_SCOPE).token

    async def ask(self, question: str, user_token: str | None = None) -> dict:
        """
        Send a question to the Foundry agent via the Responses API.

        Args:
            question: The user's question
            user_token: Optional user access token for identity passthrough (OBO).
                       If provided, this token is used instead of the CLI credential.

        Returns:
            {
                "response": str,         # Agent's text response
                "status": str,           # "success", "failed", "error"
                "tool_calls": list,      # List of tool call details
                "error": str | None,     # Error message if any
            }
        """
        if not self.is_initialized:
            return {
                "response": "",
                "status": "error",
                "tool_calls": [],
                "error": "Agent not initialized. Call initialize() first.",
            }

        for attempt in range(MAX_RETRIES + 1):
            try:
                result = await asyncio.to_thread(self._execute_question, question, user_token)

                if result["status"] == "success":
                    return result

                error = result.get("error", "")
                if self._is_retryable_error(error) and attempt < MAX_RETRIES:
                    wait = RETRY_WAIT_BASE ** (attempt + 1)
                    logger.warning(
                        f"Retryable error (attempt {attempt + 1}/{MAX_RETRIES + 1}), "
                        f"waiting {wait}s: {error}"
                    )
                    await asyncio.sleep(wait)
                    continue

                return result

            except Exception as e:
                error_str = str(e)
                logger.error(f"Agent ask error (attempt {attempt + 1}): {error_str}")

                if self._is_retryable_error(error_str) and attempt < MAX_RETRIES:
                    wait = RETRY_WAIT_BASE ** (attempt + 1)
                    logger.warning(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue

                return {
                    "response": "",
                    "status": "error",
                    "tool_calls": [],
                    "error": self._user_friendly_error(e),
                }

        return {
            "response": "",
            "status": "error",
            "tool_calls": [],
            "error": "Max retries exceeded. The Fabric Data Agent may be temporarily unavailable.",
        }

    def _execute_question(self, question: str, user_token: str | None = None) -> dict:
        """Execute a single question via the Responses API (no retries).
        
        Handles multi-turn flows: MCP tool listings and OAuth consent requests
        are auto-approved so the agent can proceed to actually answer.
        """
        # Re-discover version if TTL expired so we always target the latest
        self._refresh_version_if_stale()

        url = f"{self._endpoint}/openai/v1/responses"
        # Always use bearer token — API key doesn't support OBO tools (WorkIQ, Fabric)
        token = user_token if user_token else self._get_token()
        auth_headers = {"Authorization": f"Bearer {token}"}

        agent_ref: dict = {
            "name": self._agent_name,
            "type": "agent_reference",
        }
        if self._agent_version:
            agent_ref["version"] = self._agent_version

        payload = {
            "input": question,
            "agent_reference": agent_ref,
        }

        logger.info(f"Sending to Responses API: {question[:80]}...")

        max_continuations = 5
        for turn in range(max_continuations + 1):
            resp = http_client.post(
                url,
                headers={
                    **auth_headers,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code != 200:
                error_body = resp.text[:500]
                logger.error(f"Responses API returned {resp.status_code}: {error_body}")
                error_code = ""
                try:
                    err_data = resp.json()
                    error_code = err_data.get("error", {}).get("code", "")
                except Exception:
                    pass
                return {
                    "response": "",
                    "status": "failed",
                    "tool_calls": [],
                    "error": f"API error {resp.status_code} ({error_code}): {error_body}" if error_code else f"API error {resp.status_code}: {error_body}",
                }

            data = resp.json()

            # Check for API-level errors
            if data.get("error"):
                error_msg = json.dumps(data["error"])
                logger.error(f"Responses API error: {error_msg}")
                return {
                    "response": "",
                    "status": "failed",
                    "tool_calls": [],
                    "error": f"Agent error: {error_msg}",
                }

            # Check if we need to handle MCP approvals or OAuth consent
            output_items = data.get("output", [])
            needs_continuation = False
            continuation_input = list(output_items)  # echo all output back

            for item in output_items:
                item_type = item.get("type", "")

                if item_type == "mcp_approval_request":
                    logger.info(f"🔄 Auto-approving MCP approval request: {item.get('id', '?')}")
                    continuation_input.append({
                        "type": "mcp_approval_response",
                        "approve": True,
                        "approval_request_id": item.get("id"),
                    })
                    needs_continuation = True

                elif item_type == "oauth_consent_request":
                    logger.info(f"🔄 Auto-approving OAuth consent: {item.get('id', '?')}")
                    continuation_input.append({
                        "type": "oauth_consent_response",
                        "approve": True,
                        "consent_request_id": item.get("id"),
                    })
                    needs_continuation = True

                elif item_type == "mcp_list_tools":
                    # MCP tool listing — agent is discovering tools, just continue
                    logger.info(f"🔧 MCP list_tools received (server: {item.get('server_label', '?')})")

            if not needs_continuation:
                break

            if turn >= max_continuations:
                logger.warning("Max continuations reached — returning partial result")
                break

            logger.info(f"Continuing conversation (turn {turn + 1})...")
            response_id = data.get("id")
            payload = {
                "input": continuation_input,
                "agent_reference": agent_ref,
            }
            if response_id:
                payload["previous_response_id"] = response_id

        # Check final status
        if data.get("status") != "completed":
            status = data.get("status", "unknown")
            details = data.get("incomplete_details") or ""
            logger.warning(f"Response status: {status}, details: {details}")
            return {
                "response": "",
                "status": status,
                "tool_calls": [],
                "error": f"Agent response not completed (status={status})",
            }

        # Extract response text and tool calls from output
        response_text = ""
        tool_calls = []

        for item in data.get("output", []):
            item_type = item.get("type", "")

            if item_type == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text = content.get("text", "")
                        # Strip citation markers like 【4:0†source】
                        text = re.sub(r'【[^】]*】', '', text)
                        response_text = text.strip()

            elif item_type == "fabric_dataagent_preview_call":
                tool_calls.append({
                    "type": "fabric_dataagent",
                    "input": item.get("arguments", ""),
                    "status": item.get("status", ""),
                })

            elif item_type == "fabric_dataagent_preview_call_output":
                output_str = item.get("output", "")
                # Parse the output to extract document content
                try:
                    output_data = json.loads(output_str)
                    docs = output_data.get("documents", [])
                    for doc in docs:
                        content = doc.get("content", "")
                        if content:
                            tool_calls.append({
                                "type": "fabric_dataagent_output",
                                "content": content,
                            })
                except (json.JSONDecodeError, TypeError):
                    tool_calls.append({
                        "type": "fabric_dataagent_output",
                        "content": output_str,
                    })

        logger.info(f"Response: {response_text[:100]}... | {len(tool_calls)} tool calls")

        # Debug: log output items if no text was extracted
        if not response_text:
            for item in data.get("output", []):
                logger.warning(f"Output item: type={item.get('type')}, role={item.get('role')}, content_types={[c.get('type') for c in item.get('content', [])]}")

        return {
            "response": response_text,
            "status": "success",
            "tool_calls": tool_calls,
            "error": None,
        }

    def _is_retryable_error(self, error: str) -> bool:
        """Check if an error is transient and worth retrying."""
        retryable_patterns = [
            "rate limit", "Rate limit", "429",
            "timeout", "Timeout", "408",
            "temporarily unavailable", "503", "502", "500",
            "tool_server_error", "server_error",
            "connection reset", "connection aborted",
        ]
        return any(pattern in error for pattern in retryable_patterns)

    def _user_friendly_error(self, error: Exception) -> str:
        """Convert an exception to a user-friendly error message."""
        error_str = str(error)
        error_type = type(error).__name__

        if "404" in error_str:
            return (
                "Could not reach the Azure AI Foundry project. "
                "Please check that AZURE_PROJECT_ENDPOINT is correct."
            )

        if "401" in error_str or "Unauthorized" in error_str:
            return (
                "Azure authentication failed. Please run 'az login' "
                "to refresh your credentials."
            )

        if "403" in error_str or "Forbidden" in error_str:
            return (
                "Access denied. Your account may not have permission "
                "to access this Azure AI Foundry project."
            )

        if "Failed to retrieve data" in error_str:
            return (
                "The Fabric Data Agent could not retrieve data. "
                "This may be a transient issue — please try again."
            )

        if "tool_server_error" in error_str or "500" in error_str:
            return (
                "The data service encountered a temporary error. "
                "Please try your question again."
            )

        return f"Error querying the Data Agent: {error_type}: {error_str[:200]}"

    def _refresh_version_if_stale(self) -> None:
        """Re-discover the latest agent version when the TTL has expired."""
        if time.time() - self._version_refreshed_at < VERSION_REFRESH_SECONDS:
            return
        new_version = self._fetch_latest_agent_version()
        if new_version and new_version != self._agent_version:
            logger.info(
                f"Agent version updated: {self._agent_version} → {new_version}"
            )
            self._agent_version = new_version
        self._version_refreshed_at = time.time()

    def _fetch_latest_agent_version(self) -> Optional[str]:
        """
        Query the Foundry agents API to resolve the latest agent version.

        Tries the Foundry-native /agents/{name}/versions endpoint first,
        then falls back to the OpenAI /openai/assistants compatibility endpoint.
        Returns the version string or None if discovery fails.
        """
        version = self._fetch_version_from_foundry_api()
        if version:
            return version
        return self._fetch_version_from_assistants_api()

    def _fetch_version_from_foundry_api(self) -> Optional[str]:
        """List agent versions via the Foundry-native agents API."""
        try:
            url = f"{self._endpoint}/agents/{self._agent_name}/versions"
            token = self._get_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = http_client.get(
                url,
                headers=headers,
                params={"api-version": FOUNDRY_API_VERSION},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                versions = data.get("value", data.get("data", []))
                if versions:
                    # Pick the highest version number (most recently published)
                    try:
                        latest = max(
                            versions,
                            key=lambda v: int(v.get("version", "0")),
                        )
                    except (ValueError, TypeError):
                        latest = versions[-1]
                    ver = str(latest.get("version", ""))
                    if ver:
                        logger.debug(
                            f"Foundry agents API: latest version = {ver}"
                        )
                        return ver
            else:
                logger.debug(
                    f"Foundry agents API returned {resp.status_code}, "
                    "trying assistants API"
                )
        except Exception as e:
            logger.debug(f"Foundry agents API failed: {e}")
        return None

    def _fetch_version_from_assistants_api(self) -> Optional[str]:
        """Fall back to the OpenAI assistants compatibility endpoint."""
        try:
            url = f"{self._endpoint}/openai/assistants"
            token = self._get_token()
            resp = http_client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                params={"limit": 100, "order": "desc"},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                for assistant in data.get("data", []):
                    if assistant.get("name") == self._agent_name:
                        meta = assistant.get("metadata") or {}
                        if "version" in meta:
                            return str(meta["version"])
                        if "version" in assistant:
                            return str(assistant["version"])
                        logger.debug(
                            f"Agent '{self._agent_name}' found "
                            f"(id={assistant.get('id')}) but no version metadata"
                        )
                        break
            else:
                logger.debug(
                    f"Assistants API returned {resp.status_code}, "
                    "falling back to env version"
                )
        except Exception as e:
            logger.debug(f"Assistants API version discovery failed: {e}")
        return None

    def cleanup(self) -> None:
        """Release resources. Does NOT delete the persistent agent."""
        if self._credential:
            logger.info(f"Releasing agent runner (agent '{self._agent_name}' remains in project)")
            self._credential = None
            self._endpoint = None
            self._agent_name = None
            self._initialized = False
