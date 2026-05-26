"""
Voice Live WebSocket relay for ZavaRefundAgent.

Uses aiohttp WebSocket to connect to the Foundry Voice Live API
(cognitiveservices endpoint) and relays audio between the browser and the agent.

Flow:
  Browser mic -> PCM16 -> Frontend WS -> This relay -> Voice Live API
  Voice Live API -> audio chunks -> This relay -> Frontend WS -> Browser playback
  Voice Live API -> text events -> This relay -> Frontend WS -> UI transcript
"""
import asyncio
import json
import logging
import os

import aiohttp
from azure.identity.aio import AzureCliCredential
from fastapi import WebSocket
from response_parser import parse_agent_response

logger = logging.getLogger(__name__)

# Voice Live configuration
VOICE_LIVE_HOST = os.getenv(
    "VOICE_LIVE_HOST",
    "3iqs-aycabas-westus-resource.cognitiveservices.azure.com",
)
AGENT_NAME = os.getenv("FOUNDRY_AGENT_NAME", "Refund-agent")
_AGENT_VERSION_FALLBACK = os.getenv("FOUNDRY_AGENT_VERSION", "1")
PROJECT_NAME = os.getenv("AZURE_PROJECT_NAME", "aipmaker-project")


def _get_agent_version() -> str:
    """Get the latest agent version from the runner, falling back to env."""
    try:
        from chat import get_fabric_runner

        runner = get_fabric_runner()
        if runner and runner.is_initialized and runner.agent_version:
            return runner.agent_version
    except Exception:
        pass
    return _AGENT_VERSION_FALLBACK
VOICE_NAME = os.getenv("VOICE_NAME", "en-US-DavisNeural")


async def handle_voice_session(websocket: WebSocket) -> None:
    """
    Handle a voice session via Foundry Voice Live API.

    1. Get Azure token (ai.azure.com scope)
    2. Connect to Voice Live API (cognitiveservices endpoint)
    3. Configure session (voice, VAD, audio format)
    4. Relay audio bidirectionally between browser and API
    """
    credential = None

    try:
        credential = AzureCliCredential()
        token = (
            await credential.get_token("https://ai.azure.com/.default")
        ).token
        logger.info("Obtained Azure token for Voice Live")

        agent_version = _get_agent_version()
        url = (
            f"wss://{VOICE_LIVE_HOST}"
            f"/voice-live/realtime"
            f"?agent-name={AGENT_NAME}"
            f"&agent-version={agent_version}"
            f"&agent-project-name={PROJECT_NAME}"
            f"&api-version=2026-01-01-preview"
            f"&model={AGENT_NAME}"
            f"&authorization=Bearer+{token}"
        )

        logger.info(
            f"Connecting to Voice Live: host={VOICE_LIVE_HOST}, "
            f"agent={AGENT_NAME}:{agent_version}, project={PROJECT_NAME}"
        )

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, timeout=30) as ws:
                logger.info("Connected to Voice Live API")

                session_ready = await _do_session_handshake(ws, websocket)
                if not session_ready:
                    logger.error("Session handshake failed")
                    return

                browser_to_api = asyncio.create_task(
                    _relay_browser_to_api(websocket, ws)
                )
                api_to_browser = asyncio.create_task(
                    _relay_api_to_browser(ws, websocket)
                )

                done, pending = await asyncio.wait(
                    [browser_to_api, api_to_browser],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                for task in done:
                    exc = task.exception()
                    if exc:
                        logger.error(f"Relay task error: {exc}")

    except Exception as e:
        logger.error(f"Voice Live connection error: {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "status",
                "status": "error",
                "error": str(e),
            }))
        except Exception:
            pass
    finally:
        if credential:
            await credential.close()
        try:
            await websocket.send_text(json.dumps({
                "type": "status",
                "status": "disconnected",
            }))
        except Exception:
            pass
        logger.info("Voice session ended")


async def _do_session_handshake(
    api_ws: aiohttp.ClientWebSocketResponse,
    browser_ws: WebSocket,
) -> bool:
    """Wait for session.created, send session.update, wait for session.updated."""
    async for msg in api_ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            event = json.loads(msg.data)
            event_type = event.get("type", "")

            if event_type == "session.created":
                logger.info("Voice Live session created")
                update_msg = {
                    "type": "session.update",
                    "session": {
                        "modalities": ["text", "audio"],
                        "voice": {
                            "type": "azure-standard",
                            "name": VOICE_NAME,
                        },
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500,
                        },
                        "interim_response": {
                            "type": "llm_interim_response",
                            "triggers": ["tool", "latency"],
                            "latency_threshold_ms": 2000,
                            "instructions": (
                                "Generate a brief, friendly acknowledgment "
                                "while looking up shipment data. "
                                "Keep it natural and under 15 words."
                            ),
                            "max_completion_tokens": 50,
                        },
                    },
                }
                await api_ws.send_str(json.dumps(update_msg))
                logger.info("Session configuration sent")

            elif event_type == "session.updated":
                logger.info("Voice Live session configured successfully")
                await browser_ws.send_text(json.dumps({
                    "type": "status",
                    "status": "connected",
                }))
                return True

            elif event_type == "error":
                error = event.get("error", {})
                error_msg = error.get("message", "Unknown error")
                logger.error(f"Voice Live error during handshake: {error_msg}")
                await browser_ws.send_text(json.dumps({
                    "type": "error",
                    "error": error_msg,
                }))
                return False

        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE,
                          aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
            logger.error(f"API WebSocket closed during handshake: {msg.type}")
            return False

    return False


async def _relay_browser_to_api(
    browser_ws: WebSocket,
    api_ws: aiohttp.ClientWebSocketResponse,
):
    """Relay audio from browser to Voice Live API."""
    try:
        while True:
            data = await browser_ws.receive_text()
            message = json.loads(data)

            if message.get("type") == "audio":
                await api_ws.send_str(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": message["data"],
                }))
    except Exception as e:
        logger.info(f"Browser->API relay ended: {e}")


async def _relay_api_to_browser(
    api_ws: aiohttp.ClientWebSocketResponse,
    browser_ws: WebSocket,
):
    """Relay events from Voice Live API to browser."""
    pending_tool_args = ""
    current_user_query = ""

    try:
        async for msg in api_ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                event = json.loads(msg.data)
                event_type = event.get("type", "")

                if event_type not in ("response.audio.delta",
                                       "response.audio_transcript.delta",
                                       "response.function_call_arguments.delta"):
                    logger.info(f"Voice Live event: {event_type}")

                # Audio output
                if event_type == "response.audio.delta":
                    audio_b64 = event.get("delta", "")
                    if audio_b64:
                        await browser_ws.send_text(json.dumps({
                            "type": "audio",
                            "data": audio_b64,
                        }))

                # Assistant transcript
                elif event_type == "response.audio_transcript.delta":
                    delta = event.get("delta", "")
                    if delta:
                        await browser_ws.send_text(json.dumps({
                            "type": "transcript",
                            "role": "assistant",
                            "text": delta,
                        }))

                elif event_type == "response.audio_transcript.done":
                    transcript = event.get("transcript", "")
                    logger.info(f"Agent said: {transcript[:80]}")
                    # Parse response and send dashboard update
                    if transcript:
                        try:
                            parsed = parse_agent_response(transcript)
                            narrative = parsed.get("narrative", transcript)
                            table_data = parsed.get("table_data")
                            graph_update = parsed.get("graph_update", {})
                            new_nodes = graph_update.get("newNodes", [])
                            entity_counts: dict[str, int] = {}
                            for node in new_nodes:
                                ntype = node.get("type", "unknown")
                                entity_counts[ntype] = (
                                    entity_counts.get(ntype, 0) + 1
                                )
                            await browser_ws.send_text(json.dumps({
                                "type": "shipment_data",
                                "payload": {
                                    "tables": table_data or [],
                                    "entities": new_nodes,
                                    "entity_counts": entity_counts,
                                    "focus_query": current_user_query,
                                    "narrative": narrative or "",
                                },
                            }))
                        except Exception as e:
                            logger.warning(
                                f"Failed to parse voice response for "
                                f"dashboard: {e}"
                            )

                # User transcript
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = event.get("transcript", "")
                    if transcript:
                        current_user_query = transcript
                        await browser_ws.send_text(json.dumps({
                            "type": "transcript",
                            "role": "user",
                            "text": transcript,
                        }))

                # Speech detection
                elif event_type == "input_audio_buffer.speech_started":
                    await browser_ws.send_text(json.dumps({
                        "type": "speech_started",
                    }))

                elif event_type == "input_audio_buffer.speech_stopped":
                    await browser_ws.send_text(json.dumps({
                        "type": "speech_stopped",
                    }))

                # Tool calls
                elif event_type == "response.function_call_arguments.delta":
                    pending_tool_args += event.get("delta", "")

                elif event_type == "response.output_item.added":
                    item = event.get("item", {})
                    if item.get("type") == "function_call":
                        tool_name = item.get("name", "unknown")
                        pending_tool_args = ""
                        await browser_ws.send_text(json.dumps({
                            "type": "tool_call_start",
                            "tool": tool_name,
                        }))

                elif event_type == "response.function_call_arguments.done":
                    tool_name = event.get("name", "unknown")
                    pending_tool_args = ""
                    await browser_ws.send_text(json.dumps({
                        "type": "tool_call_end",
                        "tool": tool_name,
                    }))

                # Interim text (non-audio responses)
                elif event_type == "response.text.delta":
                    delta = event.get("delta", "")
                    if delta:
                        await browser_ws.send_text(json.dumps({
                            "type": "transcript",
                            "role": "assistant",
                            "text": delta,
                        }))

                # Errors
                elif event_type == "error":
                    error = event.get("error", {})
                    error_msg = error.get("message", "Unknown error")
                    if "no active response" not in error_msg.lower():
                        logger.error(f"Voice Live error: {error_msg}")
                        await browser_ws.send_text(json.dumps({
                            "type": "error",
                            "error": error_msg,
                        }))

            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE,
                              aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                logger.info(f"API WebSocket closed: {msg.type}")
                break

    except Exception as e:
        logger.info(f"API->Browser relay ended: {e}")
