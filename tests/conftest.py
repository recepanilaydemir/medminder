"""Shared test fixtures for MedMinder BDD tests.

Provides mock LLM, test database, and MCP server fixtures that enable
deterministic testing of the agent system without requiring API keys
or external services.

Design Decisions:
  - We test the database and MCP server layers directly (not through the
    LLM agent) so tests can run without a Gemini API key.
  - Each test gets its own isolated temporary database via `tmp_path`,
    preventing cross-test contamination.
  - The `mock_agent_response` factory allows step definitions to simulate
    ADK responses when needed for integration-level tests later.
  - Async fixtures use `pytest-asyncio` auto mode for clean event loop
    management.

⚕️ MEDICAL DISCLAIMER:
  These tests verify software behaviour only. They do NOT validate
  medical accuracy. This tool is for informational purposes only and
  is NOT a substitute for professional medical advice.
"""

from __future__ import annotations

import asyncio
import json
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Configure pytest-asyncio for auto mode so all async fixtures / tests
# are automatically detected. This avoids having to mark every async
# fixture individually.
# ---------------------------------------------------------------------------
pytest_plugins = ["pytest_asyncio"]


# ---------------------------------------------------------------------------
# Event Loop Fixture
# ---------------------------------------------------------------------------
# Provides a fresh event loop per test function. This is important because
# aiosqlite connections can leak between tests if the loop is reused.
# ---------------------------------------------------------------------------

@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create a new event loop for each test.

    Yields:
        A fresh asyncio event loop instance.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Create a temporary, isolated test database.

    Uses pytest's `tmp_path` fixture to get a unique temporary directory
    per test, ensuring complete isolation between tests. The database
    schema is initialised automatically via `init_db()`.

    Yields:
        An initialised MedMinderDB instance backed by a temporary SQLite file.
    """
    from backend.db.database import MedMinderDB

    db_path = str(tmp_path / "test_medminder.db")
    db = MedMinderDB(db_path=db_path)
    await db.init_db()
    yield db
    # Cleanup is handled automatically by tmp_path


# ---------------------------------------------------------------------------
# User Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_user_id() -> str:
    """Return a deterministic user ID for use in tests.

    Using a constant ID across tests makes step definitions simpler
    and more readable.

    Returns:
        A fixed test user ID string.
    """
    return "test_user_001"


# ---------------------------------------------------------------------------
# Sample Data Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def sample_medication(test_db, sample_user_id):
    """Create and return a pre-populated medication in the test database.

    This fixture adds a realistic Metformin entry that many scenarios
    can reference. It also ensures the owning user exists.

    Returns:
        A Medication model instance for 'Metformin 500mg twice daily'.
    """
    # Ensure the user record exists (required by FK constraint)
    await test_db.get_or_create_user(sample_user_id, "Test Patient")

    medication = await test_db.add_medication(
        user_id=sample_user_id,
        name="Metformin",
        dosage="500mg",
        frequency="twice daily",
        times=["08:00", "20:00"],
        notes="Take with food",
    )
    return medication


# ---------------------------------------------------------------------------
# Mock Agent Response Factory
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_agent_response():
    """Factory fixture for creating mock ADK agent responses.

    Returns a callable that builds a mock event object matching the
    structure of Google ADK's response format. This allows tests to
    simulate agent responses without needing a live Gemini API key.

    Usage in step definitions::

        def test_something(mock_agent_response):
            response = mock_agent_response("Here is your schedule...")
            assert response.content.parts[0].text == "Here is your schedule..."

    Returns:
        A factory function that accepts text and optional tool_calls.
    """

    def _make_response(text: str, tool_calls: list | None = None):
        """Build a mock event with the given text content.

        Args:
            text: The text content of the agent response.
            tool_calls: Optional list of mock tool call objects.

        Returns:
            A MagicMock that mimics an ADK response event.
        """
        event = MagicMock()
        part = MagicMock()
        part.text = text
        part.function_call = None

        # If tool_calls provided, attach them as additional parts
        if tool_calls:
            parts = [part]
            for tc in tool_calls:
                tool_part = MagicMock()
                tool_part.text = None
                tool_part.function_call = tc
                parts.append(tool_part)
            event.content = MagicMock()
            event.content.parts = parts
        else:
            event.content = MagicMock()
            event.content.parts = [part]

        return event

    return _make_response
