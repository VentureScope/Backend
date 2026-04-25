import asyncio
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal
from app.services.embedding_service import get_embedding_service
from app.models.user import User
from app.models.user_knowledge import UserKnowledge
from sqlalchemy import select


async def reembed_users(provider: str):
    if provider:
        os.environ["EMBEDDING_PROVIDER"] = provider
    
    embedding_service = get_embedding_service()
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.embedding.is_not(None))
        )
        users = result.scalars().all()
        
        total = len(users)
        print(f"Found {total} users with existing embeddings.")
        
        for i, user in enumerate(users, 1):
            doc = embedding_service.construct_user_document(
                career_interest=user.career_interest,
                github_profile=user.github_username,
                estudent_profile=user.estudent_profile,
                skills=user.skills,
                cv_url=user.cv_url,
            )
            
            new_embedding = embedding_service.generate_embedding(doc)
            user.embedding = new_embedding
            
            print(f"[{i}/{total}] Re-embedded user: {user.email}")
        
        await db.commit()
        
        result_knowledge = await db.execute(
            select(UserKnowledge).where(UserKnowledge.embedding.is_not(None))
        )
        chunks = result_knowledge.scalars().all()
        
        total_chunks = len(chunks)
        print(f"Found {total_chunks} knowledge chunks with existing embeddings.")
        
        for i, chunk in enumerate(chunks, 1):
            new_embedding = embedding_service.generate_embedding(chunk.content)
            chunk.embedding = new_embedding
            
            if i % 100 == 0:
                print(f"[{i}/{total_chunks}] Re-embedded knowledge chunks")
        
        await db.commit()
        
        print(f"Done! Re-embedded {total} users and {total_chunks} knowledge chunks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-generate embeddings for all users")
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Embedding provider: 'hosted' or 'hf'",
    )
    args = parser.parse_args()
    
    asyncio.run(reembed_users(args.provider))