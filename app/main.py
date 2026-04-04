"""
VentureScope API – FastAPI application entry point.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, auth, users, admin
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.token_repository import TokenRepository

logger = logging.getLogger(__name__)

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


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {"message": "VentureScope API", "docs": "/docs"}


app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
