"""
Async PostgreSQL session and engine. Repository layer uses this.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from urllib.parse import urlparse, parse_qs
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

def get_engine():
    """Create async engine with proper settings for PgBouncer."""
    database_url = settings.DATABASE_URL
    parsed_url = urlparse(database_url)
    query_params = parse_qs(parsed_url.query)
    sslmode = (query_params.get("sslmode", [""])[0] or "").lower()
    ssl_query = (query_params.get("ssl", [""])[0] or "").lower()
    use_ssl = sslmode in {"require", "verify-ca", "verify-full"} or ssl_query in {
        "true",
        "require",
    }
    if settings.ENVIRONMENT == "production":
        use_ssl = True
    if "?" in database_url:
        base, query = database_url.split("?", 1)
        params = [p for p in query.split("&") if not p.startswith("ssl=")]
        params.append("prepared_statement_cache_size=0")
        database_url = base + "?" + "&".join(params)
    else:
        database_url += "?prepared_statement_cache_size=0"
    connect_args = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }
    if use_ssl:
        connect_args["ssl"] = "require"

    return create_async_engine(
        database_url,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        connect_args=connect_args,
    )

engine = get_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """
    Dependency that provides an async database session.
    
    Successful requests are automatically committed after the caller
    finishes using the session. Rollback is automatic on exceptions.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
