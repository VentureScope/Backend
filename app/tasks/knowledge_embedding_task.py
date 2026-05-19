"""
Background task for generating knowledge chunk embeddings (transcripts, etc).
Uses synchronous SQLAlchemy (compatible with Celery workers).
"""

from app.celery_config import celery_app
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.user_knowledge import UserKnowledge
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def get_sync_engine():
    """
    Create a sync pg8000 engine for Celery tasks.

    pg8000 does not accept 'ssl' or 'sslmode' as URL query parameters —
    SSL must be passed via connect_args instead. We strip those params from
    the URL and pass ssl=True explicitly when the original URL required SSL.
    """
    from sqlalchemy.pool import NullPool
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    import ssl

    raw = settings.DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql+pg8000://')

    parsed = urlparse(raw)
    qs = parse_qs(parsed.query)

    # Detect SSL requirement from query params
    ssl_param = qs.pop('ssl', [''])[0].lower()
    sslmode_param = qs.pop('sslmode', [''])[0].lower()
    needs_ssl = ssl_param in ('true', 'require') or sslmode_param in ('require', 'verify-ca', 'verify-full')

    # Rebuild URL without ssl/sslmode params
    cleaned_query = urlencode({k: v[0] for k, v in qs.items()})
    cleaned_url = urlunparse(parsed._replace(query=cleaned_query))

    connect_args = {}
    if needs_ssl:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args['ssl_context'] = ssl_ctx

    return create_engine(cleaned_url, poolclass=NullPool, connect_args=connect_args)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_knowledge_embedding(self, knowledge_id: str):
    """
    Generate embedding for a knowledge chunk in the background.
    
    Args:
        knowledge_id: The ID of the knowledge chunk to generate embedding for
    """
    from app.services.embedding_service import get_embedding_service
    
    engine = get_sync_engine()
    
    with Session(engine) as db:
        try:
            knowledge = db.query(UserKnowledge).filter(UserKnowledge.id == knowledge_id).first()
            
            if not knowledge:
                logger.warning(f"Knowledge {knowledge_id} not found")
                return
            
            if knowledge.embedding_status == "completed":
                logger.info(f"Knowledge {knowledge_id} already has embedding")
                return
            
            try:
                embedding_service = get_embedding_service()
                knowledge.embedding = embedding_service.generate_embedding(knowledge.content)
                knowledge.embedding_status = "completed"
                db.commit()
                logger.info(f"Successfully generated embedding for knowledge {knowledge_id}")
                
            except Exception as e:
                logger.error(f"Failed to generate embedding for knowledge {knowledge_id}: {e}")
                knowledge.embedding_status = "failed"
                db.commit()
                raise self.retry(exc=e)
                
        finally:
            engine.dispose()


@celery_app.task(bind=True)
def batch_generate_knowledge_embeddings(self, user_id: str, source_type: str):
    """
    Regenerate all embeddings for a user's knowledge chunks.
    Called when user re-uploads transcripts or updates knowledge.
    
    Args:
        user_id: The ID of the user
        source_type: The source type (e.g., "transcript_course")
    """
    from app.services.embedding_service import get_embedding_service
    
    engine = get_sync_engine()
    
    with Session(engine) as db:
        try:
            knowledge_chunks = db.query(UserKnowledge).filter(
                UserKnowledge.user_id == user_id,
                UserKnowledge.source_type == source_type
            ).all()
            
            if not knowledge_chunks:
                logger.warning(f"No knowledge chunks found for user {user_id}, source {source_type}")
                return
            
            embedding_service = get_embedding_service()
            
            for chunk in knowledge_chunks:
                try:
                    chunk.embedding_status = "pending"
                    
                    chunk.embedding = embedding_service.generate_embedding(chunk.content)
                    chunk.embedding_status = "completed"
                    
                except Exception as e:
                    logger.error(f"Failed to generate embedding for chunk {chunk.id}: {e}")
                    chunk.embedding_status = "failed"
            
            db.commit()
            logger.info(f"Batch generated embeddings for user {user_id}, source {source_type}")
            
        finally:
            engine.dispose()