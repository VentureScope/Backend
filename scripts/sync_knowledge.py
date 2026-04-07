import asyncio
import os
import sys

# Add backend dir to path to allow importing app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal
from app.repositories.user_repository import UserRepository
from app.services.transcript_service import TranscriptService
from app.services.user_service import UserService
from app.services.knowledge_service import KnowledgeService
from app.schemas.academic_transcript import TranscriptCreate

async def sync_knowledge():
    """
    Sync all existing user data (profiles + transcripts) into the UserKnowledge table.
    This is necessary because existing data was not automatically ingested when
    the UserKnowledge model was introduced.
    """
    async with AsyncSessionLocal() as db:
        user_repo = UserRepository(db)
        transcript_service = TranscriptService(db)
        user_service = UserService(db)
        knowledge_service = KnowledgeService(db)
        
        # 1. Get all active users
        users = await user_repo.list_all(skip=0, limit=1000, include_inactive=False)
        print(f"Syncing knowledge for {len(users)} users...")
        
        for user in users:
            print(f"Processing User: {user.id} ({user.email})")
            
            # --- Sync Profile Chunks ---
            # Re-running _update_user_embedding will also trigger knowledge base sync for profile
            try:
                await user_service._update_user_embedding(user)
                print(f"  - Profile knowledge synced.")
            except Exception as e:
                print(f"  - Error syncing profile for {user.id}: {e}")
            
            # --- Sync Transcript Chunks ---
            try:
                latest_transcript = await transcript_service.get_latest_transcript(user.id)
                if latest_transcript:
                    # Convert raw dict from DB back to Pydantic for the helper method
                    # We need a dummy TranscriptCreate object
                    data = TranscriptCreate(
                        transcript_data=latest_transcript.transcript_data
                    )
                    chunks = transcript_service._generate_transcript_chunks(data)
                    await knowledge_service.replace_user_knowledge(
                        user.id, chunks, source_type="transcript_course"
                    )
                    print(f"  - Transcript knowledge synced ({len(chunks)} chunks).")
                else:
                    print(f"  - No transcript found.")
            except Exception as e:
                print(f"  - Error syncing transcript for {user.id}: {e}")
                
        await db.commit()
        print("\nAll knowledge synced successfully!")

if __name__ == "__main__":
    asyncio.run(sync_knowledge())
