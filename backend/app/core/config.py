import secrets
from typing import List
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: str = "development"          # development | production | test
    # No hard-coded default: required in production, auto-generated (ephemeral) in dev.
    SECRET_KEY: str = ""
    DATABASE_URL: str = "sqlite+aiosqlite:///./coldcraft.db"
    AUTO_MIGRATE: bool = True             # run `alembic upgrade head` on startup

    # ── Security ────────────────────────────────────
    # Shared token the frontend sends as `X-API-Token`. Empty = auth disabled (dev only).
    API_TOKEN: str = ""
    # Fernet key for encrypting Gmail tokens at rest. Empty = auto-created key file (dev).
    TOKEN_ENCRYPTION_KEY: str = ""
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "app://"]
    MAX_UPLOAD_BYTES: int = 6 * 1024 * 1024   # decoded screenshot size
    MAX_REQUEST_BYTES: int = 9 * 1024 * 1024  # raw request body (base64 inflates ~33%)
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_AI_PER_MINUTE: int = 20

    # ── AI providers ────────────────────────────────
    AI_PROVIDER_ORDER: List[str] = ["groq", "gemini", "openai"]
    AI_TIMEOUT_SECONDS: float = 30.0
    AI_MAX_RETRIES: int = 1               # extra attempts per provider for retryable errors
    AI_RETRY_BASE_DELAY: float = 1.0

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_VISION_MODEL: str = "gemini-3.5-flash"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # ── Prompt versions (empty = newest version on disk) ──
    PROMPT_VERSION_JOB_EXTRACTION: str = ""
    PROMPT_VERSION_JOB_EXTRACTION_VISION: str = ""
    PROMPT_VERSION_COMPANY_RESEARCH: str = ""
    PROMPT_VERSION_EMAIL_GENERATION: str = ""
    PROMPT_VERSION_FOLLOWUP: str = ""

    # ── Gmail ───────────────────────────────────────
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REDIRECT_URI: str = "http://localhost:8000/api/v1/gmail/callback"

    # ── Hunter.io ───────────────────────────────────
    HUNTER_API_KEY: str = ""

    # ── Background processing ───────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    FOLLOWUP_DEFAULT_DAYS: int = 5
    FOLLOWUP_AUTO_SEND: bool = False      # False = only mark FOLLOW_UP_DUE, user sends manually
    FOLLOWUP_CHECK_INTERVAL_MINUTES: int = 15
    INPROCESS_SCHEDULER: bool = True      # lightweight scheduler when no Celery worker is running

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if self.APP_ENV == "production":
            missing = [n for n in ("SECRET_KEY", "API_TOKEN", "TOKEN_ENCRYPTION_KEY") if not getattr(self, n)]
            if missing:
                raise ValueError(f"Missing required production settings: {', '.join(missing)}")
        elif not self.SECRET_KEY:
            self.SECRET_KEY = secrets.token_urlsafe(32)  # ephemeral, dev only
        return self

    def prompt_version(self, name: str) -> str:
        return getattr(self, f"PROMPT_VERSION_{name.upper()}", "")


settings = Settings()
