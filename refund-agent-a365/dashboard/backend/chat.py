"""
Chat Handler Module
Routes incoming WebSocket messages to the Fabric Data Agent.

Chat messages go to the Fabric Data Agent via agent_runner.py,
responses are parsed into graph updates via response_parser.py.
"""

import json
import logging
import os
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Global Fabric agent runner (lazy-initialized)
_fabric_runner = None


def get_fabric_runner():
    """Get or create the FabricAgentRunner instance."""
    global _fabric_runner
    if _fabric_runner is None:
        from agent_runner import FabricAgentRunner

        _fabric_runner = FabricAgentRunner()
    return _fabric_runner


def initialize() -> bool:
    """
    Initialize the Fabric agent.

    Called from main.py during startup.
    Returns True if initialization succeeded, False otherwise.
    """
    try:
        runner = get_fabric_runner()
        runner.initialize()
        logger.info("Fabric agent initialized")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Fabric agent: {e}")
        return False


def cleanup() -> None:
    """Clean up the Fabric agent on shutdown."""
    global _fabric_runner
    if _fabric_runner is not None:
        _fabric_runner.cleanup()
        _fabric_runner = None


async def handle_chat_message(message: dict, websocket: WebSocket) -> None:
    """
    Handle an incoming WebSocket message.

    Supports:
    - auth: Store user access token for this connection
    - control: Pause/resume (voice may need it)
    - chat: Route to Fabric Data Agent
    """
    msg_type = message.get("type")

    if msg_type == "auth":
        token = message.get("accessToken", "")
        if token:
            # Store token on the websocket object for this connection
            websocket.state.user_token = token
            logger.info("User access token received and stored for this connection")
            await websocket.send_text(json.dumps({
                "type": "auth_ok",
                "message": "Authenticated successfully"
            }))
        else:
            logger.warning("Auth message received with no token")
        return

    elif msg_type == "control":
        action = message.get("action", "")
        logger.info(f"Control action: {action}")
        # Control messages are currently a no-op without the mock engine,
        # but keep the handler for voice/future use.

    elif msg_type == "chat":
        text = message.get("message", "")
        if not text:
            return

        # Echo user message back
        await websocket.send_text(json.dumps({
            "type": "chat_message",
            "role": "user",
            "text": text
        }))

        await _handle_chat(text, websocket)

    else:
        logger.warning(f"Unknown message type: {msg_type}")


def _friendly_error(raw_error: str) -> str:
    """Convert raw API error text to a clean user-facing message."""
    if "tool_server_error" in raw_error or "500" in raw_error:
        return (
            "The data service encountered a temporary error. "
            "Please try your question again in a moment."
        )
    if "429" in raw_error or "rate limit" in raw_error.lower():
        return "The service is busy right now. Please try again in a few seconds."
    if "401" in raw_error or "Unauthorized" in raw_error:
        return "Authentication expired. The backend needs to re-authenticate."
    if "timeout" in raw_error.lower():
        return "The query took too long. Please try a simpler question."
    return "I encountered an issue querying the data. Please try again."


async def _handle_chat(text: str, websocket: WebSocket) -> None:
    """
    Handle a chat message: query the Fabric Data Agent.

    Flow:
    1. Send "tool_calling" status to frontend (triggers loading in dashboard)
    2. Query Fabric Data Agent via agent_runner
    3. Parse response into narrative + table data + entities
    4. Send chat message with narrative
    5. Send shipment_data with structured table data for dashboard
    """
    from response_parser import parse_agent_response

    runner = get_fabric_runner()

    if not runner.is_initialized:
        await websocket.send_text(json.dumps({
            "type": "chat_message",
            "role": "assistant",
            "text": "The Fabric Data Agent is not initialized. "
                    "Please check the backend logs for configuration errors."
        }))
        return

    # Get user token if available (from auth message)
    user_token = getattr(websocket.state, 'user_token', None)

    # Send tool_calling indicator (dashboard shows loading spinner)
    await websocket.send_text(json.dumps({
        "type": "tool_calling"
    }))

    # Send thinking indicator for chat panel
    await websocket.send_text(json.dumps({
        "type": "thinking",
        "text": "Querying delivery network..."
    }))

    try:
        # Query the real Fabric agent, with user token if available
        result = await runner.ask(text, user_token=user_token)

        if result.get("error"):
            error_msg = result["error"]
            logger.warning(f"Fabric agent error: {error_msg}")
            # Show a clean user-facing message, not raw API JSON
            user_msg = _friendly_error(error_msg)
            await websocket.send_text(json.dumps({
                "type": "tool_result",
                "tool": "fabric_agent",
                "result": {"error": user_msg}
            }))
            await websocket.send_text(json.dumps({
                "type": "chat_message",
                "role": "assistant",
                "text": user_msg
            }))
            return

        # Parse the response
        response_text = result.get("response", "")
        parsed = parse_agent_response(response_text)

        # Send tool_result to clear loading state
        await websocket.send_text(json.dumps({
            "type": "tool_result",
            "tool": "fabric_agent",
            "result": {}
        }))

        # Send the narrative as a chat message
        narrative = parsed.get("narrative", response_text)
        if narrative:
            await websocket.send_text(json.dumps({
                "type": "chat_message",
                "role": "assistant",
                "text": narrative
            }))

        # Build and send structured shipment data for the dashboard
        table_data = parsed.get("table_data")
        graph_update = parsed.get("graph_update", {})
        new_nodes = graph_update.get("newNodes", [])

        # Count entities by type for summary stats
        entity_counts = {}
        for node in new_nodes:
            ntype = node.get("type", "unknown")
            entity_counts[ntype] = entity_counts.get(ntype, 0) + 1

        # Always send shipment_data so the dashboard updates
        payload = {
            "tables": table_data or [],
            "entities": new_nodes,
            "entity_counts": entity_counts,
            "focus_query": text,
            "narrative": narrative or "",
            "refund_recommended": parsed.get("refund_recommended", False),
        }

        # Include route data when a refund is recommended
        if parsed.get("refund_recommended"):
            payload["package_route"] = parsed.get("package_route")
            payload["stuck_at"] = parsed.get("stuck_at")
            payload["package_id"] = parsed.get("package_id")

        await websocket.send_text(json.dumps({
            "type": "shipment_data",
            "payload": payload,
        }))
        logger.info(
            f"Sent shipment data: {len(table_data or [])} tables, "
            f"{len(new_nodes)} entities"
        )

        # Log tool calls for debugging
        tool_calls = result.get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                logger.debug(f"Fabric tool call: input={tc.get('input', '')[:100]}")

    except Exception as e:
        logger.error(f"Error in chat handler: {e}", exc_info=True)
        await websocket.send_text(json.dumps({
            "type": "tool_result",
            "tool": "fabric_agent",
            "result": {"error": str(e)}
        }))
        await websocket.send_text(json.dumps({
            "type": "chat_message",
            "role": "assistant",
            "text": "An unexpected error occurred while processing your question. "
                    "Please try again or check the backend logs."
        }))
