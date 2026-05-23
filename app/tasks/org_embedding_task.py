"""
Background task for generating organization profile embeddings.
Uses synchronous SQLAlchemy (compatible with Celery workers).

Triggered when:
  - Organization is created
  - Organization profile is updated
  - A member joins or leaves
"""

import logging
from collections import Counter

from app.celery_config import celery_app
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload
from app.models.organization import Organization, OrganizationMember, OrganizationInvite, OrganizationRoadmap
from app.models.user import User
from app.core.config import settings

# These imports are required so SQLAlchemy can resolve all relationship
# strings (e.g. "LearningRoadmap") when the mapper configures itself
# inside the Celery worker process.
from app.models.roadmap import LearningRoadmap, LearningRoadmapStep, LearningRoadmapStepResource, LearningRoadmapProgress
from app.models.experience import Experience
from app.models.oauth_account import OAuthAccount
from app.models.github_sync_snapshot import GitHubSyncSnapshot

logger = logging.getLogger(__name__)


def get_sync_engine():
    """Create a sync pg8000 engine for Celery tasks."""
    from sqlalchemy.pool import NullPool
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    import ssl

    raw = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+pg8000://")
    parsed = urlparse(raw)
    qs = parse_qs(parsed.query)

    ssl_param = qs.pop("ssl", [""])[0].lower()
    sslmode_param = qs.pop("sslmode", [""])[0].lower()
    needs_ssl = ssl_param in ("true", "require") or sslmode_param in (
        "require", "verify-ca", "verify-full"
    )

    cleaned_query = urlencode({k: v[0] for k, v in qs.items()})
    cleaned_url = urlunparse(parsed._replace(query=cleaned_query))

    connect_args = {}
    if needs_ssl:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl_context"] = ssl_ctx

    return create_engine(cleaned_url, poolclass=NullPool, connect_args=connect_args)


def _build_org_document(org: Organization, members: list) -> str:
    """
    Construct a single text document representing the organization.
    This is what gets embedded as the org's semantic vector.
    """
    parts = []

    parts.append(f"Organization: {org.display_name}")
    if org.legal_name != org.display_name:
        parts.append(f"Legal Name: {org.legal_name}")

    if org.industry:
        parts.append(f"Industry: {org.industry}")

    if org.tagline:
        parts.append(f"Tagline: {org.tagline}")

    if org.description:
        parts.append(f"Description: {org.description}")

    if org.core_services:
        services = (
            org.core_services
            if isinstance(org.core_services, list)
            else []
        )
        if services:
            parts.append(f"Core Services: {', '.join(str(s) for s in services)}")

    if org.github_orgs:
        orgs = org.github_orgs if isinstance(org.github_orgs, list) else []
        names = [g.get("name", "") if isinstance(g, dict) else str(g) for g in orgs]
        if names:
            parts.append(f"GitHub Organizations: {', '.join(names)}")

    if org.website_url:
        parts.append(f"Website: {org.website_url}")

    if members:
        parts.append(f"Headcount: {len(members)} members")

        all_skills = [
            skill
            for m in members
            for skill in ((m.user.skills or []) if m.user else [])
        ]
        if all_skills:
            top_skills = [s for s, _ in Counter(all_skills).most_common(15)]
            parts.append(f"Team Skills: {', '.join(top_skills)}")

        all_interests = [
            m.user.career_interest
            for m in members
            if m.user and m.user.career_interest
        ]
        if all_interests:
            top_interests = [i for i, _ in Counter(all_interests).most_common(5)]
            parts.append(f"Team Career Interests: {', '.join(top_interests)}")

    if not parts:
        return f"Organization: {org.display_name}"

    return "\n".join(parts)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_org_embedding(self, org_id: str):
    """
    Generate and store the semantic embedding for an organization.

    Args:
        org_id: The ID of the organization to embed.
    """
    from app.services.embedding_service import get_embedding_service

    engine = get_sync_engine()

    with Session(engine) as db:
        try:
            # Load org with members and their user profiles
            org = db.query(Organization).filter(Organization.id == org_id).first()
            if not org:
                logger.warning("Org %s not found for embedding", org_id)
                return

            members = (
                db.query(OrganizationMember)
                .filter(OrganizationMember.organization_id == org_id)
                .all()
            )
            # Manually load user for each member (sync session)
            for m in members:
                m.user = db.query(User).filter(User.id == m.user_id).first()

            # Build document text
            doc = _build_org_document(org, members)

            # Generate embedding
            try:
                embedding_service = get_embedding_service()
                org.embedding = embedding_service.generate_embedding(doc)
                org.embedding_status = "completed"
                db.commit()
                logger.info("Generated embedding for org %s", org_id)
            except Exception as e:
                logger.error("Embedding generation failed for org %s: %s", org_id, e)
                org.embedding_status = "failed"
                db.commit()
                raise self.retry(exc=e)

        finally:
            engine.dispose()
