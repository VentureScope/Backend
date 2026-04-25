"""
Background task for generating user profile embeddings.
Uses synchronous SQLAlchemy (compatible with Celery workers).
"""

from app.celery_config import celery_app
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.user import User
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def get_sync_engine():
    """Create sync engine for Celery tasks."""
    from sqlalchemy.pool import NullPool
    url = settings.DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql+pg8000://')
    return create_engine(url, poolclass=NullPool)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_user_embedding(self, user_id: str):
    """
    Generate embedding for a user profile in the background.
    
    Args:
        user_id: The ID of the user to generate embedding for
    """
    from app.services.embedding_service import get_embedding_service
    
    engine = get_sync_engine()
    
    with Session(engine) as db:
        try:
            user = db.query(User).filter(User.id == user_id).first()
            
            if not user:
                logger.warning(f"User {user_id} not found")
                return
            
            if user.embedding_status == "completed":
                logger.info(f"User {user_id} already has embedding")
                return
            
            try:
                embedding_service = get_embedding_service()
                doc = embedding_service.construct_user_document(
                    career_interest=user.career_interest,
                    github_profile=user.github_username,
                    estudent_profile=user.estudent_profile,
                    skills=user.skills,
                    cv_url=user.cv_url,
                )
                
                if doc:
                    user.embedding = embedding_service.generate_embedding(doc)
                    user.embedding_status = "completed"
                else:
                    user.embedding_status = "completed"
                
                db.commit()
                logger.info(f"Successfully generated embedding for user {user_id}")
                
            except Exception as e:
                logger.error(f"Failed to generate embedding for user {user_id}: {e}")
                user.embedding_status = "failed"
                db.commit()
                raise self.retry(exc=e)
                
        finally:
            engine.dispose()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_user_profile_embedding(self, user_id: str):
    """
    Generate embedding for user profile update in the background.
    Called when user updates their profile.
    """
    from app.services.embedding_service import get_embedding_service
    
    engine = get_sync_engine()
    
    with Session(engine) as db:
        try:
            user = db.query(User).filter(User.id == user_id).first()
            
            if not user:
                logger.warning(f"User {user_id} not found for profile update")
                return
            
            try:
                user.embedding_status = "pending"
                db.commit()
                
                embedding_service = get_embedding_service()
                doc = embedding_service.construct_user_document(
                    career_interest=user.career_interest,
                    github_profile=user.github_username,
                    estudent_profile=user.estudent_profile,
                    skills=user.skills,
                    cv_url=user.cv_url,
                )
                
                if doc:
                    user.embedding = embedding_service.generate_embedding(doc)
                    user.embedding_status = "completed"
                else:
                    user.embedding_status = "completed"
                
                db.commit()
                logger.info(f"Successfully generated embedding for user {user_id}")
                
            except Exception as e:
                logger.error(f"Failed to generate embedding for user {user_id}: {e}")
                user.embedding_status = "failed"
                db.commit()
                raise self.retry(exc=e)
                
        finally:
            engine.dispose()