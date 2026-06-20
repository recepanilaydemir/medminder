"""
MedMinder Configuration Management
===================================

Loads application settings from environment variables and .env file.
Uses a dataclass-based approach for type safety and validation, keeping
dependencies minimal (no pydantic-settings required — just stdlib + dotenv).

Usage:
    from config import get_settings
    settings = get_settings()
    print(settings.GOOGLE_API_KEY)

MEDICAL DISCLAIMER:
    This application is for informational purposes only and does not
    constitute medical advice. Always consult a qualified healthcare
    professional for medical decisions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Load .env file from the backend directory (where this file lives)
# override=False means real env vars take precedence over .env values
# ---------------------------------------------------------------------------
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path, override=False)


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


@dataclass(frozen=True)
class Settings:
    """
    Immutable application settings loaded from environment variables.

    Attributes:
        GOOGLE_API_KEY: Gemini API key for the agent framework.
                        Required for any agent / LLM operations.
        DB_PATH:        Path to the SQLite database file.
        HOST:           Host address the FastAPI server binds to.
        PORT:           Port number the FastAPI server listens on.
        DEBUG:          Enable debug mode (verbose logging, auto-reload).
        GOOGLE_OAUTH_CREDENTIALS:
                        Path to the Google OAuth client-secrets JSON file.
                        Optional — only needed for Google Calendar integration.
    """

    GOOGLE_API_KEY: str = ""
    DB_PATH: str = "./medminder.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    GOOGLE_OAUTH_CREDENTIALS: Optional[str] = None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self, *, require_api_key: bool = True) -> None:
        """
        Validate that all required configuration values are present.

        Args:
            require_api_key: If True (default), raises ConfigurationError
                             when GOOGLE_API_KEY is empty.  Pass False for
                             tasks that don't need the Gemini API (e.g.
                             running database migrations or tests with
                             mocked LLM calls).

        Raises:
            ConfigurationError: When a required setting is missing or
                                obviously invalid.
        """
        errors: list[str] = []

        if require_api_key and not self.GOOGLE_API_KEY:
            errors.append(
                "GOOGLE_API_KEY is required. "
                "Get one at https://aistudio.google.com/ and add it to "
                "your .env file."
            )

        if self.PORT < 1 or self.PORT > 65535:
            errors.append(
                f"PORT must be between 1 and 65535, got {self.PORT}."
            )

        # If an OAuth credentials path is set, warn (don't fail) if missing
        if self.GOOGLE_OAUTH_CREDENTIALS:
            creds_path = Path(self.GOOGLE_OAUTH_CREDENTIALS)
            if not creds_path.exists():
                # Not an error — the user may set it up later
                import warnings
                warnings.warn(
                    f"GOOGLE_OAUTH_CREDENTIALS points to "
                    f"'{self.GOOGLE_OAUTH_CREDENTIALS}' which does not exist. "
                    f"Google Calendar integration will be unavailable.",
                    stacklevel=2,
                )

        if errors:
            raise ConfigurationError(
                "Configuration errors:\n  • " + "\n  • ".join(errors)
            )


def _parse_bool(value: str) -> bool:
    """Convert common boolean string representations to bool."""
    return value.strip().lower() in ("true", "1", "yes", "on")


def get_settings() -> Settings:
    """
    Build a Settings instance from the current environment.

    This function reads os.environ (which includes values loaded from .env
    by dotenv at module import time) and returns an immutable Settings
    dataclass.

    Returns:
        A fully-populated Settings instance.
    """
    return Settings(
        GOOGLE_API_KEY=os.getenv("GOOGLE_API_KEY", ""),
        DB_PATH=os.getenv("DB_PATH", "./medminder.db"),
        HOST=os.getenv("HOST", "0.0.0.0"),
        PORT=int(os.getenv("PORT", "8000")),
        DEBUG=_parse_bool(os.getenv("DEBUG", "false")),
        GOOGLE_OAUTH_CREDENTIALS=os.getenv("GOOGLE_OAUTH_CREDENTIALS"),
    )
