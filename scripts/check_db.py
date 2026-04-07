import asyncio
import os
import sys

# Add backend dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT user_id, COUNT(*) FROM user_knowledge GROUP BY user_id"))
        rows = result.fetchall()
        print("User Knowledge counts by user:")
        if not rows:
            print("  (Table is completely empty!)")
        for row in rows:
            print(f"  User {row[0]}: {row[1]} chunks")

if __name__ == "__main__":
    asyncio.run(main())
