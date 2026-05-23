"""
Application configuration via environment variables.
"""

import json
import logging
import os
from typing import Any, List, Union
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator
from functools import lru_cache

_config_logger = logging.getLogger(__name__)

_INSECURE_SECRET_KEY = "change-me-in-production-use-openssl-rand-hex-32"
_DEFAULT_DATABASE_URL = "postgresql+asyncpg://venturescope:venturescope@localhost:5432/venturescope"


def load_env_file():
    """Manually load .env file if pydantic-settings doesn't work properly."""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
    )
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key not in os.environ:  # Don't override existing env vars
                        os.environ[key] = value


# Load .env file manually if needed
load_env_file()


class Settings(BaseSettings):
    PROJECT_NAME: str = "VentureScope"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://venturescope:venturescope@localhost:5432/venturescope"
    )

    # JWT
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Token cleanup settings
    TOKEN_CLEANUP_INTERVAL_SECONDS: int = 3600  # 1 hour default

    # OAuth Configuration
    # Google OAuth 2.0 settings
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/oauth/google/callback"

    # GitHub OAuth settings
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/auth/oauth/github/callback"

    # OAuth state management (for CSRF protection)
    OAUTH_STATE_SECRET: str = ""  # Should be different from JWT SECRET_KEY
    OAUTH_STATE_EXPIRE_MINUTES: int = 10  # Short expiration for security

    # OAuth scope configuration
    GOOGLE_OAUTH_SCOPES: List[str] = ["openid", "email", "profile"]
    GITHUB_OAUTH_SCOPES: List[str] = ["read:user", "user:email", "repo"]

    # Environment setting
    ENVIRONMENT: str = "development"  # development, staging, production

    # CORS Configuration
    # Frontend URLs that are allowed to make requests to this API
    # In development: Can be "*" or specific origins
    # In production: Should be specific origins only
    CORS_ORIGINS: Union[str, List[str]] = Field(
        default="*",  # Allow all origins in development by default
        description="Comma-separated string or JSON list of allowed CORS origins",
    )

    # Primary frontend URL (used in production if CORS_ORIGINS not set)
    FRONTEND_URL: str = "http://localhost:3000"

    # Additional CORS settings
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "HEAD",
    ]
    CORS_ALLOW_HEADERS: List[str] = [
        "Accept",
        "Accept-Encoding",
        "Authorization",
        "Content-Type",
        "DNT",
        "Origin",
        "User-Agent",
        "X-CSRFToken",
        "X-Requested-With",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> Union[str, List[str]]:
        """
        Parse CORS origins from various formats:
        - "*" for all origins
        - Comma-separated string: "http://localhost:3000,http://localhost:5173"
        - JSON array string: '["http://localhost:3000","http://localhost:5173"]'
        - Python list: ["http://localhost:3000", "http://localhost:5173"]
        """
        if isinstance(v, str):
            # Check if it's a special value
            if v == "*":
                return "*"

            # Try to parse as JSON first
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

            # Parse as comma-separated string
            if "," in v:
                return [origin.strip() for origin in v.split(",") if origin.strip()]

            # Single origin
            return [v.strip()] if v.strip() else "*"

        if isinstance(v, list):
            return v

        return "*"  # Default fallback

    def get_cors_origins(self) -> Union[str, List[str]]:
        """
        Get CORS origins based on environment.

        Development: Allow all origins (*) by default for easier development
        Production: Use specific origins only for security
        """
        if self.ENVIRONMENT == "development":
            # In development, if CORS_ORIGINS is "*", allow all origins
            if self.CORS_ORIGINS == "*":
                return "*"
            # If specific origins are set, use them (allows overriding in dev)
            elif isinstance(self.CORS_ORIGINS, list):
                return self.CORS_ORIGINS
            else:
                return "*"

        elif self.ENVIRONMENT == "production":
            # In production, never allow "*" for security
            if self.CORS_ORIGINS == "*":
                # Use FRONTEND_URL as fallback
                return [self.FRONTEND_URL]
            elif isinstance(self.CORS_ORIGINS, list):
                # Filter out any "*" entries and localhost origins for security
                origins = []
                for origin in self.CORS_ORIGINS:
                    if origin != "*" and not any(
                        dev_indicator in origin.lower()
                        for dev_indicator in ["localhost", "127.0.0.1"]
                    ):
                        origins.append(origin)

                # If no valid origins remain, use FRONTEND_URL
                if not origins:
                    origins = [self.FRONTEND_URL]

                return origins
            else:
                return [self.FRONTEND_URL]

        # Default for other environments (staging, etc.)
        else:
            if isinstance(self.CORS_ORIGINS, list):
                return self.CORS_ORIGINS
            elif self.CORS_ORIGINS == "*":
                return [self.FRONTEND_URL]
            else:
                return [self.FRONTEND_URL]

    # Embeddings
    EMBEDDING_PROVIDER: str = "hosted"
    EMBEDDING_MODEL_NAME: str = "intfloat/e5-base-v2"
    EMBEDDING_DIMENSIONS: int = 768

    # Chat / LLM completions
    CHAT_MODEL_NAME: str = "gpt-4o-mini"
    CHAT_MAX_TOKENS: int = 800
    CHAT_TEMPERATURE: float = 0.7

    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "venturescope-cvs"
    S3_ENDPOINT_URL: str = ""
    S3_PROFILE_PICTURE_BUCKET: str = "photo"
    S3_ORG_BUCKET: str = "organization"

    # Upstash Redis – HTTP client (used by OTP service, rate limiting)
    UPSTASH_REDIS_URL: str = ""
    UPSTASH_REDIS_TOKEN: str = ""

    # Celery broker / result backend – wire-protocol rediss:// URL from Upstash
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # Supabase direct read connection (for admin dashboard queries)
    SUPABASE_URL: str = ""  # psycopg2-compatible DSN for Supabase PostgreSQL

    # Airflow REST API (for admin pipeline proxy)
    AIRFLOW_API_URL: str = ""                    # e.g. http://airflow-webserver:8080/api/v1
    AIRFLOW_SERVICE_ACCOUNT_USER: str = ""
    AIRFLOW_SERVICE_ACCOUNT_PASSWORD: str = ""

    # Sentry
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "production"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.2
    SENTRY_AUTH_TOKEN: str = ""      # Internal integration token — project:read + org:read
    SENTRY_ORG_SLUG: str = ""        # e.g. venturescope
    SENTRY_PROJECT_SLUG: str = ""    # e.g. venturescope
    SENTRY_WEBHOOK_SECRET: str = ""  # Shared secret for verifying inbound Sentry webhooks

    # Pipeline webhook secret (CareerCompass → Backend HMAC-SHA256)
    PIPELINE_WEBHOOK_SECRET: str = ""

    # DO Spaces (S3-compatible) — scoped to models/ prefix for ML model deploy
    DO_SPACES_KEY: str = ""
    DO_SPACES_SECRET: str = ""
    DO_SPACES_REGION: str = "lon1"
    DO_SPACES_BUCKET: str = ""
    DO_SPACES_ENDPOINT: str = ""  # e.g. https://lon1.digitaloceanspaces.com
    # Legacy: kept for backward-compat; no longer used at runtime
    REDIS_URL: str = ""

    # Email / OTP Configuration
    EMAIL_PROVIDER: str = "mailgun"  # mailgun | (extendable: sendgrid, smtp, ...)
    MAILGUN_API_KEY: str = ""
    MAILGUN_DOMAIN: str = ""
    MAILGUN_FROM_EMAIL: str = "noreply@mg.venturescope.app"
    MAILGUN_API_BASE_URL: str = (
        "https://api.mailgun.net/v3"  # EU: https://api.eu.mailgun.net/v3
    )

    # OTP settings
    OTP_EXPIRE_MINUTES: int = 10
    OTP_RESEND_COOLDOWN_SECONDS: int = 60  # min seconds between resends
    OTP_MAX_RESENDS_PER_HOUR: int = 3  # hard cap per rolling hour

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """
        In production: crash immediately if insecure defaults are detected.
        In development: emit a loud warning so developers notice.
        """
        is_production = self.ENVIRONMENT == "production"

        issues: list[str] = []

        if self.SECRET_KEY == _INSECURE_SECRET_KEY:
            issues.append(
                "SECRET_KEY is still the placeholder value — "
                "generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

        if self.DATABASE_URL == _DEFAULT_DATABASE_URL:
            issues.append(
                "DATABASE_URL is still the hardcoded local default — "
                "set it to your actual database connection string"
            )

        if issues:
            if is_production:
                raise ValueError(
                    "Refusing to start in production with insecure configuration:\n"
                    + "\n".join(f"  • {i}" for i in issues)
                )
            for issue in issues:
                _config_logger.warning("INSECURE CONFIG: %s", issue)

        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
