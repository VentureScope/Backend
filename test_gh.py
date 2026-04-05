import asyncio
from app.services.github_service import fetch_github_profile_description

async def main():
    desc = await fetch_github_profile_description("torvalds")
    print(desc)

asyncio.run(main())
