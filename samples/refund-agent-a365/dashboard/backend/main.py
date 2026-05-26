"""
FabricIQ Foundry Viz Backend
FastAPI application with WebSocket endpoints for chat and voice interactions.

Connects to a persistent Foundry agent for live Fabric Data Agent queries.
Optionally sends traces to Azure Application Insights via OpenTelemetry.
"""

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from chat import handle_chat_message, initialize, cleanup
from voice import handle_voice_session

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    logger.info("Refund Agent backend starting...")

    # Configure Azure Monitor / App Insights tracing
    app_insights_conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if app_insights_conn:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor
            configure_azure_monitor(connection_string=app_insights_conn)
            logger.info("App Insights tracing configured")
        except ImportError:
            logger.warning(
                "azure-monitor-opentelemetry not installed — tracing disabled. "
                "Run: pip install azure-monitor-opentelemetry"
            )
    else:
        logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set — tracing disabled")

    # Initialize the Fabric agent
    logger.info("Initializing Fabric Data Agent...")
    agent_ok = initialize()
    if not agent_ok:
        logger.error(
            "Failed to initialize Fabric agent. "
            "Check AZURE_PROJECT_ENDPOINT and FOUNDRY_AGENT_NAME in backend/.env"
        )

    logger.info("Server running on http://localhost:8000")
    logger.info("Chat WebSocket at ws://localhost:8000/ws")
    logger.info("Voice WebSocket at ws://localhost:8000/voice")

    yield

    # Shutdown
    logger.info("Refund Agent backend shutting down...")
    cleanup()
    logger.info("Fabric agent cleaned up")


app = FastAPI(
    title="Refund Agent",
    description="Refund agent with Foundry backend",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS for frontend development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve built frontend static files in production
_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_has_static = os.path.isdir(_static_dir)


@app.get("/")
async def root():
    """Serve frontend index.html or health check."""
    if _has_static:
        from fastapi.responses import FileResponse
        return FileResponse(os.path.join(_static_dir, "index.html"))
    return {
        "status": "ok",
        "service": "shipment-dashboard",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for chat interactions.

    Message types:
    - {"type": "auth", "accessToken": "..."} — must be sent first
    - {"type": "control", "action": "pause|resume"}
    - {"type": "chat", "message": "Where has PKG-1234 been?"}
    """
    await websocket.accept()
    logger.info("Chat WebSocket connection established")

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received: {data[:100]}...")

            try:
                message = json.loads(data)
                await handle_chat_message(message, websocket)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "error": f"Invalid JSON: {str(e)}"
                }))

    except WebSocketDisconnect:
        logger.info("Chat WebSocket connection closed")
    except Exception as e:
        logger.error(f"Chat WebSocket error: {e}")


@app.websocket("/voice")
async def voice_endpoint(websocket: WebSocket):
    """WebSocket endpoint for voice interactions with gpt-realtime."""
    await websocket.accept()
    logger.info("Voice WebSocket connection established")
    try:
        await handle_voice_session(websocket)
    except WebSocketDisconnect:
        logger.info("Voice WebSocket connection closed")
    except Exception as e:
        logger.error(f"Voice WebSocket error: {e}")


# Mount frontend static assets (JS, CSS, icons) — must be after API routes
if _has_static:
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")
    app.mount("/icons", StaticFiles(directory=os.path.join(_static_dir, "icons") if os.path.isdir(os.path.join(_static_dir, "icons")) else _static_dir), name="icons")

    # Catch-all for SPA routing — serve index.html for any unmatched route
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        from fastapi.responses import FileResponse
        file_path = os.path.join(_static_dir, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_static_dir, "index.html"))
