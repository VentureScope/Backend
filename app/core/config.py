"""
Application configuration via environment variables.
"""

import json
import os
from typing import Any, List, Union
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from functools import lru_cache


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
    GITHUB_OAUTH_SCOPES: List[str] = ["read:user", "user:email"]

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

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
