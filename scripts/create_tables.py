"""
One-off: create PostgreSQL tables from SQLAlchemy models.
Run from backend/: python scripts/create_tables.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import engine, Base
from app.models import User  # noqa: F401 - load models so they're registered


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created.")


if __name__ == "__main__":
    asyncio.run(main())
