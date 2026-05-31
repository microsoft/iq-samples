# Copyright (c) Microsoft. All rights reserved.

"""
Refund Agent — Bridges to an existing Azure AI Foundry agent.

Instead of running its own LLM, this agent forwards messages to a Foundry agent
that already has instructions, model config, and IQ connections (Foundry IQ for
refund policies, Fabric IQ for order data). The A365 hosting layer adds Teams
integration, notifications, and observability.

Uses the OpenAI Responses API via the Foundry applications protocol endpoint.
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Enable GenAI tracing before importing OpenAI
os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"

# Configure Azure Monitor tracing → Foundry Application Insights
_appinsights_conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if _appinsights_conn:
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry import trace

    configure_azure_monitor(connection_string=_appinsights_conn)
    _tracer = trace.get_tracer(__name__)
    logging.getLogger(__name__).info("📊 Tracing enabled → Application Insights")
else:
    _tracer = None
    logging.getLogger(__name__).warning("⚠️ APPLICATIONINSIGHTS_CONNECTION_STRING not set — tracing disabled")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from agent_interface import AgentInterface
from contextlib import nullcontext
from openai import OpenAI
from microsoft_agents.hosting.core import Authorization, TurnContext
from microsoft_agents_a365.notifications.agent_notification import NotificationTypes

_API_VERSION = "2025-11-15-preview"

# Item types the Responses API accepts as *input*. When continuing after an MCP
# approval we re-submit the prior output, but tool-specific output items (e.g. a
# Fabric Data Agent call item) are NOT valid input and trigger
# `400 invalid_value ... input[N]`. We filter resubmitted items to this set so
# only replayable items (messages, reasoning, approval requests, etc.) are sent.
_ALLOWED_INPUT_ITEM_TYPES = {
    "apply_patch_call", "apply_patch_call_output", "code_interpreter_call",
    "compaction", "compaction_trigger", "computer_call", "computer_call_output",
    "custom_tool_call", "custom_tool_call_output", "file_search_call",
    "function_call", "function_call_output", "image_generation_call",
    "item_reference", "local_shell_call", "local_shell_call_output",
    "mcp_approval_request", "mcp_approval_response", "mcp_call", "mcp_list_tools",
    "message", "reasoning", "shell_call", "shell_call_output",
    "tool_search_call", "tool_search_output", "web_search_call",
}


class RefundAgent(AgentInterface):
    """
    A365-hosted agent that delegates to an existing Foundry agent.

    The Foundry agent handles refund logic (instructions, Foundry IQ, Fabric IQ).
    This wrapper adds A365 capabilities: Teams messaging, notifications, observability.
    Communicates via the OpenAI Responses API (Foundry applications protocol).
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        # Foundry connection config
        self.endpoint = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT", "").rstrip("/")
        self.agent_name = os.getenv("FOUNDRY_AGENT_NAME")
        self._model = os.getenv("FOUNDRY_MODEL_NAME", "gpt-4.1-mini-1")

        if not self.endpoint:
            raise ValueError("AZURE_AI_FOUNDRY_ENDPOINT environment variable is required")
        if not self.agent_name:
            raise ValueError("FOUNDRY_AGENT_NAME environment variable is required")

        self._api_key = os.getenv("AZURE_AI_SERVICES_KEY") or None

        self._base_url = f"{self.endpoint}/openai"

        # Agent reference — tells Foundry which agent to use
        self._agent_ref = {"type": "agent_reference", "name": self.agent_name}

        # Default client (API key if available, otherwise bare) — used for startup ping
        default_headers = {}
        if self._api_key:
            default_headers["api-key"] = self._api_key
        self._default_client = OpenAI(
            api_key="unused",
            base_url=self._base_url,
            default_query={"api-version": _API_VERSION},
            default_headers=default_headers,
        )

        # Per-user conversation history for context continuity
        # (applications protocol is stateless — no previous_response_id support)
        self._conversations: dict[str, list] = {}

    def _get_client_for_user(self, user_token: Optional[str] = None) -> OpenAI:
        """
        Return an OpenAI client authenticated with the user's OBO token (for identity
        passthrough to Fabric Data Agent / Work IQ), or the default API key client.
        """
        if user_token:
            return OpenAI(
                api_key="unused",
                base_url=self._base_url,
                default_query={"api-version": _API_VERSION},
                default_headers={"Authorization": f"Bearer {user_token}"},
            )
        return self._default_client

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    async def initialize(self) -> None:
        """Verify connectivity to the Foundry agent (non-fatal on failure)."""
        logger.info(f"🔌 Connecting to Foundry agent '{self.agent_name}' at {self.endpoint} ...")

        try:
            response = self._default_client.responses.create(
                model=self._model,
                input="ping",
                extra_body={"agent_reference": self._agent_ref},
            )
            logger.info(
                f"✅ Foundry agent '{self.agent_name}' is reachable "
                f"(model: {response.model}, status: {response.status})"
            )
        except Exception as e:
            logger.warning(
                f"⚠️ Foundry agent ping failed (will retry on first message): {e}"
            )

    async def cleanup(self) -> None:
        """Release client resources."""
        if self._default_client:
            self._default_client.close()
        logger.info("🧹 Agent cleanup completed")

    # =========================================================================
    # MESSAGE PROCESSING
    # =========================================================================

    async def process_user_message(
        self,
        message: str,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> str:
        """Forward the user message to the Foundry agent and return its response."""
        from_prop = context.activity.from_property
        user_id = getattr(from_prop, "id", "default") if from_prop else "default"
        display_name = getattr(from_prop, "name", None) or "unknown"
        logger.info(f"📨 Message from {display_name} ({user_id}): {message[:80]}...")

        span_ctx = _tracer.start_as_current_span(
            "process_user_message",
            attributes={"user_id": user_id, "display_name": display_name, "message": message[:200]},
        ) if _tracer else nullcontext()

        with span_ctx:
            try:
                # Exchange user token for OBO access (Fabric Data Agent + Work IQ)
                user_token = await self._exchange_user_token(auth, auth_handler_name, context)
                return self._call_foundry(user_id, message, user_token=user_token)
            except Exception as e:
                logger.error(f"❌ Error processing message: {e}", exc_info=True)
                self._conversations.pop(user_id, None)
                return f"Sorry, I encountered an error: {str(e)}"

    # =========================================================================
    # NOTIFICATION HANDLING
    # =========================================================================

    async def handle_agent_notification_activity(
        self,
        notification_activity,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> str:
        """Handle A365 notifications (email, Word comments) by forwarding to the Foundry agent."""
        try:
            notification_type = notification_activity.notification_type
            logger.info(f"📬 Processing notification: {notification_type}")

            if notification_type == NotificationTypes.EMAIL_NOTIFICATION:
                email = notification_activity.email
                email_body = getattr(email, "html_body", "") or getattr(email, "body", "")
                message = (
                    "You received the following email about a refund request. "
                    "Please review and process it.\n\n"
                    f"{email_body}"
                )
            elif notification_type == NotificationTypes.WPX_COMMENT:
                comment_text = notification_activity.text or ""
                message = (
                    f"You were mentioned in a Word document comment: {comment_text}\n"
                    "Please review and respond."
                )
            else:
                message = notification_activity.text or f"Notification received: {notification_type}"

            return await self.process_user_message(message, auth, auth_handler_name, context)

        except Exception as e:
            logger.error(f"❌ Notification error: {e}")
            return f"Sorry, I encountered an error processing the notification: {str(e)}"

    # =========================================================================
    # OBO TOKEN EXCHANGE (Fabric Data Agent + Work IQ require user delegation)
    # =========================================================================

    _FOUNDRY_USER_SCOPES = os.getenv(
        "FOUNDRY_USER_TOKEN_SCOPES",
        "https://ai.azure.com/.default",
    )

    async def _exchange_user_token(
        self, auth: Authorization, auth_handler_name: Optional[str], context: TurnContext
    ) -> Optional[str]:
        """
        Get a user-delegated token via the AgenticUserAuthorization handler.

        The A365 platform (with inheritable permissions configured on the blueprint)
        provides user-delegated tokens through get_agentic_user_token(). This token
        allows Fabric Data Agent and Work IQ to access data on behalf of the Teams user.
        """
        import jwt as pyjwt

        scopes = [s.strip() for s in self._FOUNDRY_USER_SCOPES.split(",") if s.strip()]
        logger.info(f"🔑 Attempting token exchange — scopes={scopes}, handler={auth_handler_name}")

        # Log activity context for debugging
        activity = context.activity
        is_agentic = activity.is_agentic_request() if hasattr(activity, "is_agentic_request") else "unknown"
        agentic_user = activity.get_agentic_user() if hasattr(activity, "get_agentic_user") else "unknown"
        logger.info(f"🔍 Activity: is_agentic={is_agentic}, agentic_user={agentic_user}")

        if auth_handler_name:
            try:
                token_response = await auth.exchange_token(
                    context,
                    scopes=scopes,
                    auth_handler_id=auth_handler_name,
                )
                if token_response and token_response.token:
                    # Decode to inspect — is this a user token or app token?
                    try:
                        claims = pyjwt.decode(token_response.token, options={"verify_signature": False})
                        logger.info(
                            f"🔍 TOKEN CLAIMS: oid={claims.get('oid')}, "
                            f"upn={claims.get('upn', claims.get('preferred_username', 'NONE'))}, "
                            f"aud={claims.get('aud')}, "
                            f"has_scp={'scp' in claims}, scp={claims.get('scp', 'NONE')}, "
                            f"app_id={claims.get('appid', claims.get('azp', 'NONE'))}, "
                            f"idtyp={claims.get('idtyp', 'NONE')}"
                        )
                    except Exception as decode_err:
                        logger.warning(f"⚠️ Could not decode token: {decode_err}")

                    logger.info(f"✅ User token acquired via agentic handler (len={len(token_response.token)})")
                    return token_response.token
                else:
                    logger.warning(f"⚠️ Token exchange returned empty response: {token_response}")
            except Exception as e:
                logger.warning(f"⚠️ Agentic handler token exchange failed: {e}", exc_info=True)

        logger.warning("⚠️ No user token available — calling Foundry with API key (Fabric will fail)")
        return None

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _call_foundry(self, user_id: str, message: str, user_token: Optional[str] = None) -> str:
        """Call the Foundry Responses API and return the assistant's text."""
        # Build input with conversation history for context continuity
        history = self._conversations.get(user_id, [])
        history.append({"type": "message", "role": "user", "content": message})

        # Use user-authenticated client for OBO passthrough (Fabric + Work IQ)
        client = self._get_client_for_user(user_token)

        response = client.responses.create(
            model=self._model,
            input=history,
            extra_body={"agent_reference": self._agent_ref},
        )

        # Log all MCP tool calls and their outputs for debugging
        for item in response.output:
            item_type = getattr(item, "type", "?")
            if "mcp" in item_type:
                item_dict = item.model_dump() if hasattr(item, "model_dump") else str(item)
                logger.info(f"🔧 MCP item: type={item_type}, data={str(item_dict)[:500]}")

        # Handle MCP approval requests — auto-approve and continue
        max_approvals = 5
        while max_approvals > 0:
            approval_items = [
                item for item in response.output
                if getattr(item, "type", None) == "mcp_approval_request"
            ]
            if not approval_items:
                break
            
            logger.info(f"🔄 Auto-approving {len(approval_items)} MCP tool request(s)")
            # Build approval responses. Only re-submit output items that are valid
            # as Responses API input — skip non-replayable tool-call items (e.g. a
            # Fabric Data Agent call) which would cause `400 invalid_value`.
            approval_input = []
            for item in response.output:
                item_type = getattr(item, "type", None)
                if item_type in _ALLOWED_INPUT_ITEM_TYPES:
                    approval_input.append(item)
                else:
                    logger.info(f"⏭️ Skipping non-replayable output item: type={item_type}")
            for item in approval_items:
                approval_input.append({
                    "type": "mcp_approval_response",
                    "approve": True,
                    "approval_request_id": item.id,
                })
            
            response = client.responses.create(
                model=self._model,
                input=history + approval_input,
                extra_body={"agent_reference": self._agent_ref},
            )
            max_approvals -= 1

        # Append only message items to history (skip MCP/tool metadata items)
        for item in response.output:
            if getattr(item, "role", None) and getattr(item, "type", None) == "message":
                history.append(item)
        self._conversations[user_id] = history

        # Extract assistant text from output
        for item in response.output:
            if getattr(item, "role", None) == "assistant" and getattr(item, "type", None) == "message":
                texts = [c.text for c in item.content if c.type == "output_text"]
                if texts:
                    return "\n".join(texts)

        # Log what we actually got for debugging
        output_types = [(getattr(i, "type", "?"), getattr(i, "role", "?")) for i in response.output]
        logger.warning(f"⚠️ No assistant message found in response. Output items: {output_types}")
        # Try to find any text content in any item
        for item in response.output:
            content = getattr(item, "content", None)
            if content:
                for c in content:
                    text = getattr(c, "text", None)
                    if text:
                        return text

        return "I processed your request but couldn't generate a response."
