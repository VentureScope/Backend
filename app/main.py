"""
VentureScope API – FastAPI application entry point.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import (
    health, auth, users, admin, transcript_configs, transcripts,
    chat, notifications, mfa, jobs, roadmap, resume,
    admin_ml, admin_taxonomy, admin_system, admin_sentry,
)
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.token_repository import TokenRepository
from app.services.supabase_service import close_pool as close_supabase_pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentry SDK initialisation (no-op if SENTRY_DSN is empty)
# ---------------------------------------------------------------------------
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        server_name="backend-api",
        environment=settings.SENTRY_ENVIRONMENT,
        integrations=[FastApiIntegration()],
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    )
    logger.info("Sentry SDK initialised (environment=%s)", settings.SENTRY_ENVIRONMENT)

# Background task control
_cleanup_task: asyncio.Task | None = None


async def cleanup_expired_tokens():
    """
    Background task that periodically cleans up expired tokens from the blocklist.

    Runs at the interval specified in settings.TOKEN_CLEANUP_INTERVAL_SECONDS.
    """
    while True:
        try:
            await asyncio.sleep(settings.TOKEN_CLEANUP_INTERVAL_SECONDS)
            async with AsyncSessionLocal() as db:
                repo = TokenRepository(db)
                count = await repo.cleanup_expired()
                if count > 0:
                    logger.info(f"Cleaned up {count} expired tokens from blocklist")
        except asyncio.CancelledError:
            logger.info("Token cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Error during token cleanup: {e}")
            # Continue running even if there's an error


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    global _cleanup_task

    # Startup
    _cleanup_task = asyncio.create_task(cleanup_expired_tokens())
    logger.info("Started token blocklist cleanup background task")

    yield

    # Shutdown
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("Stopped token blocklist cleanup background task")

    await close_supabase_pool()
    logger.info("Closed Supabase connection pool")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS with environment-appropriate settings
cors_origins = settings.get_cors_origins()

# Log CORS configuration for debugging
logger.info(f"CORS Configuration:")
logger.info(f"  Environment: {settings.ENVIRONMENT}")
logger.info(f"  Origins: {cors_origins}")
logger.info(f"  Allow Credentials: {settings.CORS_ALLOW_CREDENTIALS}")
logger.info(f"  Allow Methods: {settings.CORS_ALLOW_METHODS}")

# Security warning for development
if cors_origins == "*":
    logger.warning(
        "CORS configured to allow ALL origins (*). "
        "This should ONLY be used in development!"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
    expose_headers=[
        "Content-Length",
        "Content-Range",
        "Content-Type",
        "Date",
        "Server",
        "Transfer-Encoding",
    ],
)


@app.get("/")
def root() -> dict:
    return {"message": "VentureScope API", "docs": "/docs"}


app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(mfa.router, prefix="/api/auth/mfa", tags=["mfa"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(transcript_configs.router)
app.include_router(transcripts.router)
app.include_router(chat.router)
app.include_router(notifications.router)
app.include_router(jobs.router)
app.include_router(roadmap.router)
app.include_router(resume.router)

# Phase 2 — Super-admin dashboard endpoints
app.include_router(admin_ml.router, prefix="/api/admin", tags=["admin-ml"])
app.include_router(admin_taxonomy.router, prefix="/api/admin", tags=["admin-taxonomy"])
app.include_router(admin_system.router, prefix="/api/admin", tags=["admin-system"])
app.include_router(admin_sentry.router, prefix="/api/admin", tags=["admin-sentry"])

# Phase 4 — Prometheus metrics endpoint (/metrics, scraped by Prometheus)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
