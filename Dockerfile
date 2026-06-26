# =============================================================================
# MedMinder Dockerfile — Multi-Stage Build
# =============================================================================
#
# Builds the MedMinder application in two stages:
#   1. Builder stage: Installs Python dependencies into a clean layer
#   2. Runtime stage: Copies only what's needed for a slim final image
#
# Multi-stage builds reduce the final image size by excluding build tools,
# pip caches, and other artifacts that aren't needed at runtime.
#
# Usage:
#   docker build -t medminder .
#   docker run -p 8000:8000 -e GOOGLE_API_KEY=your-key medminder
#
# Or use docker-compose (recommended):
#   docker-compose up --build
#
# ⚕️ MEDICAL DISCLAIMER:
#   MedMinder is for informational and educational purposes only.
#   It is NOT a substitute for professional medical advice.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — Install Python dependencies
# ---------------------------------------------------------------------------
# We use a separate builder stage so that pip, wheel, setuptools, and any
# C compiler toolchains needed for native extensions don't bloat the final
# image. Only the installed site-packages are copied forward.
FROM python:3.11-slim AS builder

WORKDIR /app

# Copy only requirements first to leverage Docker's layer caching.
# If requirements.txt hasn't changed, Docker reuses the cached layer
# and skips the expensive pip install step entirely.
COPY backend/requirements.txt .

# Install Python dependencies.
# --no-cache-dir: Don't store pip's download cache (saves ~50MB+ in image size)
# --user: Install to /root/.local so we can copy a clean directory
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime — Slim production image
# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Install Node.js for MCP servers that require it:
#   - healthcare-mcp-public (npm package)
#   - Google Calendar MCP (npm package)
# Also install curl for the Docker health check endpoint.
# Clean up apt cache to keep the image small.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        nodejs \
        npm \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the builder stage.
# This includes all pip-installed libraries (google-adk, fastapi, etc.)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source code.
# Order matters for cache efficiency — less frequently changed files first.
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create a data directory for the SQLite database.
# Using a named volume (see docker-compose.yml) means data persists
# across container restarts and rebuilds.
RUN mkdir -p /app/data /app/.cache /app/.local

# Security: run as non-root user.
# The medminder user owns /app so that external MCP subprocesses
# (BioMCP/uvx, npm packages) can write their cache and config files.
RUN groupadd -r medminder && useradd -r -g medminder -d /app -s /sbin/nologin medminder \
    && chown -R medminder:medminder /app
USER medminder

# Set HOME and cache directories so external MCP subprocesses
# (uvx, npm, pip) write to the writable /app directory.
ENV HOME=/app
ENV XDG_CACHE_HOME=/app/.cache

# Set default DB path to the writable data directory.
# DB_PATH is used by backend/config.py (FastAPI server).
# MEDMINDER_DB_PATH is used by backend/mcp_servers/medminder_server.py (MCP).
ENV DB_PATH=/app/data/medminder.db
ENV MEDMINDER_DB_PATH=/app/data/medminder.db

# Expose the FastAPI server port.
# This is documentation — the actual port binding happens in docker run or
# docker-compose.yml with the -p flag.
EXPOSE 8000

# Health check — Docker will mark the container as unhealthy if this fails.
# The /api/health endpoint returns basic server status without requiring
# an API key, making it suitable for infrastructure monitoring.
#
# Parameters:
#   --interval=30s:  Check every 30 seconds
#   --timeout=10s:   Fail if the check takes longer than 10 seconds
#   --start-period=15s: Give the app 15s to start before checking
#   --retries=3:     Mark unhealthy after 3 consecutive failures
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run the FastAPI server via Python module execution.
# This ensures proper package resolution (backend.server imports work).
# The server binds to 0.0.0.0:8000 by default (configured in backend/config.py).
CMD ["python", "-m", "backend.server"]
