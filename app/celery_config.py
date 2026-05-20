"""
Celery configuration for background embedding tasks.
"""

from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "embedding_tasks",
    broker=settings.CELERY_BROKER_URL or settings.REDIS_URL,
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
    # Explicit task includes — guarantees every task module is loaded at
    # worker startup regardless of autodiscovery package scanning.
    include=[
        "app.tasks.user_embedding_task",
        "app.tasks.knowledge_embedding_task",
        "app.tasks.org_embedding_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_track_started=True,
    task_default_retry_delay=60,
    task_max_retries=3,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
)