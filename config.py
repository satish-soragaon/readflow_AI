"""
Central configuration for ReadFlow AI.

All settings are driven by environment variables so the app can be deployed
to any environment without changing code.  Copy .env.example → .env and
fill in the values for local development.
"""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    # ── Security ──────────────────────────────────────────────────────────────
    # Must be overridden by a long random string in production.
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-readflow-change-me")

    # Restrict session cookies to HTTPS in production.
    SESSION_COOKIE_SECURE: bool = os.environ.get("FLASK_ENV") == "production"
    SESSION_COOKIE_HTTPONLY: bool = True
    # "Lax" protects against CSRF for top-level navigations while allowing
    # same-site redirects (e.g. OAuth flows).
    SESSION_COOKIE_SAMESITE: str = "Lax"

    # ── CSRF (Flask-WTF) ──────────────────────────────────────────────────────
    WTF_CSRF_ENABLED: bool = True
    WTF_CSRF_TIME_LIMIT: int = 7200  # 2-hour token validity

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_PATH: Path = Path(
        os.environ.get("DATABASE_PATH", str(BASE_DIR / "readflow.db"))
    )

    # ── File uploads ──────────────────────────────────────────────────────────
    UPLOAD_DIR: Path = Path(
        os.environ.get("UPLOAD_DIR", str(BASE_DIR / "uploads"))
    )
    # Flask uses UPLOAD_FOLDER internally; keep both in sync.
    UPLOAD_FOLDER: Path = UPLOAD_DIR
    MAX_CONTENT_LENGTH: int = int(
        os.environ.get("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024))
    )
    ALLOWED_EXTENSIONS: frozenset = frozenset(
        {"pdf", "docx", "txt", "jpg", "jpeg", "png", "webp"}
    )

    # ── AI providers ──────────────────────────────────────────────────────────
    # "disabled" | "anthropic" | "openai"
    DEFAULT_AI_PROVIDER: str = os.environ.get("AI_PROVIDER", "disabled")

    ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY") or None
    # Model used when AI_PROVIDER=anthropic
    ANTHROPIC_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")

    OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY") or None
    OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o")

    # ── Rate limiting (Flask-Limiter) ─────────────────────────────────────────
    # Use "redis://localhost:6379/0" in production for persistence across workers.
    RATELIMIT_STORAGE_URI: str = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
