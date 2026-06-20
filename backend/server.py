"""
MedMinder FastAPI Server
========================

The web backend that bridges the frontend UI with the ADK multi-agent system.
This single server handles everything: API endpoints, agent orchestration,
database queries, and static file serving — no separate frontend server needed.

Architecture Overview::

    ┌──────────────┐     ┌──────────┐     ┌────────────┐     ┌────────────┐
    │  Frontend    │────▶│  FastAPI  │────▶│ ADK Runner │────▶│   Agents   │
    │  (HTML/JS)   │◀────│  Server   │◀────│            │◀────│  (Gemini)  │
    └──────────────┘     └──────────┘     └────────────┘     └────────────┘
                              │                                     │
                              │  Direct DB queries                  │  MCP Servers
                              ▼                                     ▼
                        ┌──────────┐                         ┌────────────┐
                        │  SQLite  │◀────────────────────────│ MCP Tools  │
                        └──────────┘                         └────────────┘

Endpoints:
    POST /api/chat           — Send a message to the MedMinder agent system
    POST /api/config         — Set the Gemini API key (stored in memory)
    GET  /api/config         — Check whether an API key is currently configured
    GET  /api/medications    — List medications (direct DB query, bypasses agent)
    GET  /api/schedule/today — Get today's schedule (direct DB query)
    GET  /api/health         — Health check for monitoring
    GET  /                   — Serve the frontend single-page application

⚕️ MEDICAL DISCLAIMER:
    MedMinder is for INFORMATIONAL and EDUCATIONAL purposes only. It is NOT a
    substitute for professional medical advice, diagnosis, or treatment. Always
    seek the advice of a qualified healthcare provider with any questions
    regarding medications or medical conditions. Never disregard professional
    medical advice or delay seeking it because of information provided by this
    application.

Security Note (Development vs Production):
    This server uses several patterns that are acceptable for a demo/capstone
    project but should be hardened for production use:
    - API keys are stored in memory (use a secrets manager in production)
    - CORS allows all origins (restrict to your domain in production)
    - No rate limiting (add rate limiting middleware in production)
    - No authentication system (add OAuth2/JWT in production)
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ADK (Agent Development Kit) imports for running the multi-agent system
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Local imports — our own modules
from backend.agents.orchestrator import create_root_agent
from backend.config import get_settings
from backend.db.database import MedMinderDB

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
# We configure logging early so all modules inherit the same format.
# Level is set to DEBUG if the config says so, otherwise INFO.
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", "false").lower() in ("true", "1") else logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("medminder.server")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Resolve the project root directory relative to this file's location.
# server.py lives in backend/, so project root is one level up.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FRONTEND_DIR = _PROJECT_ROOT / "frontend"

# The ADK application name — used by Runner to identify the agent app.
_APP_NAME = "medminder"

# Default user ID for the single-user demo. In a production system, this
# would come from an authentication layer (JWT, session cookie, etc.).
_DEFAULT_USER_ID = "default_user"

# ---------------------------------------------------------------------------
# In-Memory API Key Storage
# ---------------------------------------------------------------------------
# WHY IN-MEMORY?
# The Gemini API key needs to be available as an environment variable for the
# ADK Runner (the google.adk library reads `GOOGLE_API_KEY` from os.environ
# internally — this is an ADK design choice, not ours). For this demo, we
# let the user paste their API key in the frontend, and we store it in a
# simple dict. A production system would use:
#   - A secrets manager (Google Secret Manager, AWS Secrets Manager, etc.)
#   - Per-user key management with encryption at rest
#   - Server-side key storage (never expose keys to the client)
#
# We use a mutable dict so that the lifespan function and endpoints can
# share state without global variable reassignment issues.
_api_key_store: dict[str, str] = {
    # "global" key is the fallback for all requests; individual session keys
    # could override this in a multi-user setup.
}

# ---------------------------------------------------------------------------
# Cached Agent & Runner
# ---------------------------------------------------------------------------
# WHY CACHE THE AGENT AND RUNNER?
# Creating the ADK agent hierarchy involves:
#   1. Parsing agent definitions and tool schemas
#   2. Setting up MCP server connections
#   3. Building the internal agent graph
# This is expensive and only needs to happen once (or when config changes).
# We cache the agent and runner so subsequent /api/chat requests reuse them.
#
# The cache is invalidated when:
#   - The API key changes (different key might mean different model access)
#   - The server restarts (cache is in-memory only)
_cached_agent: Any = None
_cached_runner: Any = None
_cached_session_service: Optional[InMemorySessionService] = None


# ---------------------------------------------------------------------------
# Pydantic Request/Response Models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    """Request body for the POST /api/chat endpoint.

    Attributes:
        message: The user's natural-language message to send to the agent.
        session_id: Optional session ID for conversation continuity. If not
                    provided, a new session is created. Returning the same
                    session_id in subsequent requests maintains conversation
                    context (the agent remembers previous messages).
        user_id: Identifier for the user. Defaults to 'default_user' for
                 the single-user demo.
    """

    message: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The user's message to the MedMinder agent.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation continuity. Omit to start a new conversation.",
    )
    user_id: str = Field(
        default=_DEFAULT_USER_ID,
        description="User identifier (defaults to 'default_user' for the demo).",
    )


class ConfigRequest(BaseModel):
    """Request body for the POST /api/config endpoint.

    Attributes:
        api_key: The Google Gemini API key to use for LLM operations.
                 Get one at https://aistudio.google.com/
    """

    api_key: str = Field(
        ...,
        min_length=1,
        description="Google Gemini API key.",
    )


# ---------------------------------------------------------------------------
# FastAPI Lifespan (Startup / Shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle.

    On startup:
        1. Load application settings from environment / .env file
        2. Initialize the SQLite database (create tables if needed)
        3. Store the DB instance on app.state for endpoint access
        4. Pre-load the API key from .env if available

    On shutdown:
        1. Log shutdown (cleanup is automatic — SQLite connections are
           per-operation in our async pattern, so nothing to close)

    Using FastAPI's lifespan context manager (recommended over the older
    @app.on_event decorators which are deprecated in newer FastAPI versions).
    """
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("  🏥 MedMinder Server Starting Up")
    logger.info("=" * 60)

    settings = get_settings()

    # Initialize the database — creates tables if they don't exist.
    # The DB path comes from settings (environment variable or default).
    db = MedMinderDB(db_path=settings.DB_PATH)
    await db.init_db()
    logger.info("Database initialized at: %s", settings.DB_PATH)

    # Store the DB instance on app.state so endpoints can access it
    # without importing a global. This is a FastAPI best practice for
    # sharing resources across the application.
    app.state.db = db

    # If an API key is already in the environment (from .env file),
    # pre-populate our in-memory store so the user doesn't have to
    # paste it in the frontend.
    if settings.GOOGLE_API_KEY:
        _api_key_store["global"] = settings.GOOGLE_API_KEY
        logger.info("API key loaded from environment configuration.")
    else:
        logger.warning(
            "No GOOGLE_API_KEY found in environment. "
            "The user must provide one via the frontend configuration."
        )

    logger.info("Frontend directory: %s", _FRONTEND_DIR)
    logger.info("Server ready at http://%s:%d", settings.HOST, settings.PORT)
    logger.info("=" * 60)

    yield  # ← Application runs here

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("🏥 MedMinder Server shutting down. Goodbye!")


# ---------------------------------------------------------------------------
# FastAPI Application Instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="MedMinder API",
    description=(
        "Medication tracking and health management API powered by Google's "
        "Agent Development Kit (ADK). Provides both conversational AI endpoints "
        "and direct database access for the dashboard.\n\n"
        "⚕️ **Medical Disclaimer**: This application is for informational "
        "purposes only and does not constitute medical advice."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
# Allow all origins during development so the frontend can talk to the API
# regardless of how it's served (e.g., file://, localhost:3000, etc.).
#
# ⚠️ PRODUCTION WARNING: Restrict `allow_origins` to your actual domain(s)
# in production. Allowing all origins ("*") means any website can make
# requests to your API, which is a security risk.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # Allows X-API-Key header from frontend
)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def _get_api_key(request: Request) -> str:
    """Extract the API key from the request or fall back to stored config.

    Resolution order:
        1. X-API-Key request header (per-request override)
        2. Stored 'global' key (set via POST /api/config or .env)

    Args:
        request: The incoming FastAPI request.

    Returns:
        The API key string.

    Raises:
        HTTPException: 401 if no API key is found anywhere.
    """
    # Check the X-API-Key header first (allows per-request key override)
    header_key = request.headers.get("X-API-Key", "").strip()
    if header_key:
        return header_key

    # Fall back to the stored global key
    stored_key = _api_key_store.get("global", "").strip()
    if stored_key:
        return stored_key

    # No key found — the user hasn't configured one yet
    raise HTTPException(
        status_code=401,
        detail={
            "error": "API key not configured",
            "message": (
                "Please set your Google Gemini API key. You can either:\n"
                "1. Use the settings panel in the frontend\n"
                "2. POST to /api/config with your key\n"
                "3. Set GOOGLE_API_KEY in your .env file\n\n"
                "Get a free API key at: https://aistudio.google.com/"
            ),
        },
    )


def _get_or_create_agent_and_runner(api_key: str) -> tuple[Any, Runner, InMemorySessionService]:
    """Get the cached agent/runner or create new ones.

    We cache the agent and runner because:
        - Agent creation involves parsing tool schemas and setting up MCP
          server connections, which is expensive (~1-3 seconds)
        - The Runner maintains session state through InMemorySessionService
        - Recreating on every request would lose conversation context

    The cache is invalidated when the API key changes, because a different
    key might provide access to different models or have different quotas.

    Args:
        api_key: The Gemini API key to use.

    Returns:
        Tuple of (root_agent, runner, session_service).
    """
    global _cached_agent, _cached_runner, _cached_session_service

    # WHY SET os.environ['GOOGLE_API_KEY']?
    # The ADK library (google.adk) reads the API key from the environment
    # variable GOOGLE_API_KEY internally. There's no way to pass it
    # programmatically to the Runner constructor. This is an ADK design
    # decision — the library assumes the key is in the environment.
    #
    # Setting it here (just before agent creation) ensures the correct key
    # is used. In a multi-user system, you'd need to be more careful about
    # thread safety here — but for a single-user demo, this is fine.
    os.environ["GOOGLE_API_KEY"] = api_key

    # Return cached instances if they exist (agent is already built)
    if _cached_agent is not None and _cached_runner is not None and _cached_session_service is not None:
        return _cached_agent, _cached_runner, _cached_session_service

    logger.info("Creating new agent and runner (first request or cache invalidated)...")

    # Build the root agent — this sets up the entire multi-agent hierarchy
    # (orchestrator → medication agent, health agent, etc.) and connects
    # to MCP servers for tool access.
    root_agent = create_root_agent()

    # InMemorySessionService stores conversation history in RAM.
    # Sessions persist across requests within the same server process,
    # enabling multi-turn conversations. They're lost on server restart.
    session_service = InMemorySessionService()

    # The Runner is the ADK's execution engine. It:
    #   1. Routes messages to the appropriate agent
    #   2. Manages tool calls and function responses
    #   3. Handles multi-turn conversation flow
    #   4. Collects response events for streaming
    runner = Runner(
        agent=root_agent,
        app_name=_APP_NAME,
        session_service=session_service,
    )

    # Cache for subsequent requests
    _cached_agent = root_agent
    _cached_runner = runner
    _cached_session_service = session_service

    logger.info("Agent and runner created successfully.")
    return root_agent, runner, session_service


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


# ── Health Check ─────────────────────────────────────────────────────────────
@app.get(
    "/api/health",
    summary="Health check",
    description="Returns server status and basic diagnostics.",
    tags=["System"],
)
async def health_check() -> JSONResponse:
    """Health check endpoint for monitoring and load balancers.

    Returns basic server status information. This endpoint does NOT
    require an API key — it's meant for infrastructure monitoring.
    """
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "MedMinder API",
            "version": "1.0.0",
            "api_key_configured": bool(_api_key_store.get("global")),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


# ── API Key Configuration ───────────────────────────────────────────────────
@app.post(
    "/api/config",
    summary="Set API key",
    description="Store the Gemini API key for agent operations.",
    tags=["Configuration"],
)
async def set_api_key(config: ConfigRequest) -> JSONResponse:
    """Store the Gemini API key in memory.

    This endpoint receives the API key from the frontend settings panel
    and stores it in the in-memory key store. The key is used for all
    subsequent agent interactions.

    Security considerations for this demo:
        - The key is stored in plain text in memory (acceptable for local demo)
        - The key is transmitted over the network (use HTTPS in production)
        - No validation of the key format is performed (we let the API fail
          gracefully if the key is invalid)

    In production, you would:
        - Never accept API keys from the frontend
        - Store keys in a secrets manager (Google Secret Manager, Vault, etc.)
        - Use per-user API key management with encryption at rest
        - Implement key rotation policies
    """
    global _cached_agent, _cached_runner, _cached_session_service

    # Store the key globally (single-user demo pattern)
    _api_key_store["global"] = config.api_key

    # Also set it in the environment so ADK can find it immediately
    os.environ["GOOGLE_API_KEY"] = config.api_key

    # Invalidate the cached agent/runner so they're recreated with the
    # new key on the next request. This handles the case where the user
    # changes their key mid-session (e.g., because the old one expired).
    _cached_agent = None
    _cached_runner = None
    _cached_session_service = None

    logger.info("API key configured successfully (key length: %d chars).", len(config.api_key))

    return JSONResponse(
        content={
            "status": "configured",
            "message": "API key saved successfully. You can now chat with MedMinder.",
        }
    )


@app.get(
    "/api/config",
    summary="Check API key status",
    description="Check whether a Gemini API key has been configured.",
    tags=["Configuration"],
)
async def get_api_key_status() -> JSONResponse:
    """Check if an API key is currently configured.

    Returns whether a key exists — never returns the actual key value.
    The frontend uses this to decide whether to show the setup wizard
    or the main chat interface.
    """
    has_key = bool(_api_key_store.get("global"))

    return JSONResponse(
        content={
            "configured": has_key,
            "message": (
                "API key is configured and ready."
                if has_key
                else "No API key configured. Please set one to use MedMinder."
            ),
        }
    )


# ── Chat Endpoint (Core) ────────────────────────────────────────────────────
@app.post(
    "/api/chat",
    summary="Chat with MedMinder",
    description=(
        "Send a natural-language message to the MedMinder agent system. "
        "The agent can manage medications, log doses, track symptoms, "
        "and generate health reports."
    ),
    tags=["Chat"],
)
async def chat(request: Request, chat_request: ChatRequest) -> JSONResponse:
    """Process a chat message through the ADK multi-agent system.

    This is the core endpoint that connects the frontend to the AI agents.
    The flow is:
        1. Validate the API key (from header or stored config)
        2. Set GOOGLE_API_KEY environment variable (ADK requirement)
        3. Get or create the agent hierarchy and Runner
        4. Get or create a session for conversation continuity
        5. Build an ADK Content message from the user's text
        6. Run the agent asynchronously, collecting response events
        7. Extract text from response events and return to the frontend

    Args:
        request: The FastAPI request (used to extract X-API-Key header).
        chat_request: The validated chat request body.

    Returns:
        JSON response with the agent's reply, session ID, and metadata.

    Raises:
        HTTPException: 401 if no API key, 500 if agent error.
    """
    # Step 1: Get and validate the API key
    api_key = _get_api_key(request)

    logger.info(
        "Chat request — user: %s, session: %s, message length: %d",
        chat_request.user_id,
        chat_request.session_id or "(new session)",
        len(chat_request.message),
    )

    try:
        # Step 2-3: Ensure API key is in env and get/create agent + runner
        _, runner, session_service = _get_or_create_agent_and_runner(api_key)

        # Step 4: Get or create a session
        # The session_id ties together a conversation history. If the frontend
        # sends the same session_id across requests, the agent remembers the
        # previous context (medications discussed, etc.).
        session_id = chat_request.session_id or f"session_{chat_request.user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Try to get an existing session, or create a new one
        session = await session_service.get_session(
            app_name=_APP_NAME,
            user_id=chat_request.user_id,
            session_id=session_id,
        )

        if session is None:
            # No existing session — create a new one
            session = await session_service.create_session(
                app_name=_APP_NAME,
                user_id=chat_request.user_id,
                session_id=session_id,
            )
            logger.info("Created new session: %s", session_id)
        else:
            logger.info("Reusing existing session: %s", session_id)

        # Step 5: Build the user message in ADK's Content format
        # The ADK expects messages as types.Content objects with a role
        # and parts list. Each part can be text, function calls, etc.
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=chat_request.message)],
        )

        # Step 6: Run the agent and collect response events
        # runner.run_async() is an async generator that yields events as
        # the agent processes the message. Events can include:
        #   - Text responses from the LLM
        #   - Tool/function call results
        #   - Sub-agent delegations
        #   - Error events
        response_parts: list[str] = []

        async for event in runner.run_async(
            user_id=chat_request.user_id,
            session_id=session_id,
            new_message=user_message,
        ):
            # Each event has an `author` (which agent produced it) and
            # `content` (the actual response). We collect text parts from
            # all events to build the complete response.
            if event.content and event.content.parts:
                for part in event.content.parts:
                    # Only collect text parts — skip function_call and
                    # function_response parts (those are internal to the
                    # agent system and not meant for the user).
                    if hasattr(part, "text") and part.text:
                        response_parts.append(part.text)
                        logger.debug(
                            "Response part from '%s': %s",
                            event.author,
                            part.text[:100] + "..." if len(part.text) > 100 else part.text,
                        )

        # Step 7: Combine all text parts into the final response
        if response_parts:
            # Use the last substantive response — earlier parts may be
            # intermediate agent thinking or sub-agent responses that get
            # refined by the orchestrator.
            agent_response = response_parts[-1]
        else:
            # No text response — this can happen if the agent only made
            # tool calls without generating a text summary.
            agent_response = (
                "I processed your request, but I don't have a text response. "
                "This might mean an internal tool was called. Please try rephrasing "
                "your question."
            )

        logger.info(
            "Chat response — session: %s, response length: %d",
            session_id,
            len(agent_response),
        )

        return JSONResponse(
            content={
                "response": agent_response,
                "session_id": session_id,
                "user_id": chat_request.user_id,
                "disclaimer": (
                    "⚕️ This response is for informational purposes only "
                    "and does not constitute medical advice."
                ),
            }
        )

    except HTTPException:
        # Re-raise HTTP exceptions (like 401 from _get_api_key)
        raise

    except Exception as e:
        # Catch all other exceptions and return a helpful error message.
        # In a production system, you'd want to distinguish between:
        #   - User errors (bad input) → 4xx
        #   - Server errors (agent crash) → 5xx
        #   - External errors (API quota, network) → 502/503
        logger.error(
            "Agent error during chat: %s\n%s",
            str(e),
            traceback.format_exc(),
        )

        # Provide specific guidance based on common error patterns
        error_message = str(e)
        if "API_KEY" in error_message.upper() or "unauthorized" in error_message.lower():
            detail = (
                "Your API key appears to be invalid or expired. "
                "Please check your key at https://aistudio.google.com/ "
                "and update it via the settings panel."
            )
            status_code = 401
        elif "quota" in error_message.lower() or "rate" in error_message.lower():
            detail = (
                "API rate limit or quota exceeded. Please wait a moment "
                "and try again, or check your API usage at "
                "https://aistudio.google.com/"
            )
            status_code = 429
        else:
            detail = (
                f"An error occurred while processing your message: {error_message}\n\n"
                "This might be a temporary issue. Please try again. If the problem "
                "persists, check the server logs for more details."
            )
            status_code = 500

        raise HTTPException(status_code=status_code, detail=detail)


# ── Direct Database Endpoints ───────────────────────────────────────────────
# WHY DIRECT DB ENDPOINTS ALONGSIDE THE AGENT?
#
# The MedMinder agent (via ADK) is powerful but adds latency:
#   - LLM inference: 1-5 seconds per request
#   - Tool routing: Additional round-trips for function calls
#   - Context building: Agent reads conversation history
#
# For simple, predictable queries like "show me my medications" or "what's
# my schedule today", going through the agent is overkill. These direct DB
# endpoints provide:
#   1. **Speed**: ~10ms vs ~3-5 seconds through the agent
#   2. **Reliability**: No LLM variability — same query, same result
#   3. **Cost savings**: No API tokens consumed for simple data retrieval
#
# The dashboard uses these fast endpoints for real-time data display,
# while the chat interface uses the agent for complex interactions like
# "add a new medication" or "how's my adherence this month?"


@app.get(
    "/api/medications",
    summary="List medications",
    description="Retrieve all active medications for a user directly from the database.",
    tags=["Dashboard"],
)
async def list_medications(
    request: Request,
    user_id: str = Query(
        default=_DEFAULT_USER_ID,
        description="User ID to list medications for.",
    ),
) -> JSONResponse:
    """List all active medications for a user.

    This endpoint queries the database directly (no agent involved) for
    fast, predictable responses. Used by the dashboard to populate the
    medication list on page load.

    Args:
        request: FastAPI request (used to access app.state.db).
        user_id: The user whose medications to retrieve.

    Returns:
        JSON response with a list of active medications.
    """
    try:
        db: MedMinderDB = request.app.state.db
        medications = await db.list_medications(user_id)

        # Convert Pydantic models to dicts for JSON serialization
        med_list = [med.model_dump() for med in medications]

        logger.info(
            "Listed %d medications for user '%s' (direct DB query).",
            len(med_list),
            user_id,
        )

        return JSONResponse(
            content={
                "medications": med_list,
                "count": len(med_list),
                "user_id": user_id,
            }
        )

    except Exception as e:
        logger.error("Error listing medications: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve medications: {str(e)}",
        )


@app.get(
    "/api/schedule/today",
    summary="Today's schedule",
    description="Get today's medication schedule with dose completion status.",
    tags=["Dashboard"],
)
async def get_todays_schedule(
    request: Request,
    user_id: str = Query(
        default=_DEFAULT_USER_ID,
        description="User ID to get the schedule for.",
    ),
) -> JSONResponse:
    """Get today's medication schedule with completion tracking.

    Returns each active medication with its scheduled times and how many
    doses have been logged today. Used by the dashboard to show the
    daily medication checklist.

    Args:
        request: FastAPI request (used to access app.state.db).
        user_id: The user whose schedule to retrieve.

    Returns:
        JSON response with today's schedule and completion status.
    """
    try:
        db: MedMinderDB = request.app.state.db
        schedule = await db.get_todays_schedule(user_id)

        logger.info(
            "Retrieved today's schedule for user '%s': %d medications (direct DB query).",
            user_id,
            len(schedule),
        )

        return JSONResponse(
            content={
                "schedule": schedule,
                "count": len(schedule),
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "user_id": user_id,
            }
        )

    except Exception as e:
        logger.error("Error retrieving schedule: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve today's schedule: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Static File Serving (Frontend)
# ---------------------------------------------------------------------------
# Serve the frontend directory as static files. This means the entire
# MedMinder application (frontend + backend + agents) runs from a single
# server — no need for a separate frontend server (Vite, webpack-dev-server,
# etc.). This simplifies deployment and is ideal for a demo/capstone project.
#
# The frontend is a vanilla HTML/CSS/JS application — no build step required.
# Just open the browser to http://localhost:8000 and everything works.

# Mount static files for CSS, JS, and other assets.
# The /frontend path prefix means requests like /frontend/css/style.css
# will serve files from the frontend/css/ directory.
if _FRONTEND_DIR.exists():
    app.mount(
        "/frontend",
        StaticFiles(directory=str(_FRONTEND_DIR)),
        name="frontend_static",
    )
    logger.info("Frontend static files mounted from: %s", _FRONTEND_DIR)
else:
    logger.warning(
        "Frontend directory not found at %s. "
        "Static file serving is disabled. "
        "The API endpoints will still work.",
        _FRONTEND_DIR,
    )


@app.get(
    "/",
    summary="Serve frontend",
    description="Serve the MedMinder frontend application.",
    tags=["Frontend"],
    include_in_schema=False,  # Hide from API docs — it's the UI, not an API
)
async def serve_frontend() -> FileResponse:
    """Serve the main frontend HTML page.

    This is the entry point for the web application. When a user visits
    http://localhost:8000/, they get the MedMinder frontend which
    communicates with the API endpoints defined above.
    """
    index_path = _FRONTEND_DIR / "index.html"

    if not index_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Frontend not found. The index.html file is missing from "
                f"'{_FRONTEND_DIR}'. Please ensure the frontend directory "
                "is properly set up."
            ),
        )

    return FileResponse(
        path=str(index_path),
        media_type="text/html",
    )


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
# When running this file directly (python -m backend.server or python backend/server.py),
# start the uvicorn ASGI server with the app instance.
#
# In production, you'd use a process manager like gunicorn with uvicorn workers:
#   gunicorn backend.server:app -w 4 -k uvicorn.workers.UvicornWorker
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    logger.info(
        "Starting MedMinder server on %s:%d (reload=%s)",
        settings.HOST,
        settings.PORT,
        settings.DEBUG,
    )

    uvicorn.run(
        "backend.server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
