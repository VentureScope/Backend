"""
Application configuration via environment variables.
"""

import json
from typing import Any, List, Union
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from functools import lru_cache


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
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSIONS: int = 384

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
