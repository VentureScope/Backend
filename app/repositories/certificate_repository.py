"""
Repository for Certificate CRUD operations.
"""

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.certificate import Certificate


class CertificateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, certificate_id: str) -> Certificate | None:
        result = await self.db.execute(
            select(Certificate).where(Certificate.id == certificate_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: str) -> list[Certificate]:
        result = await self.db.execute(
            select(Certificate)
            .where(Certificate.user_id == user_id)
            .order_by(Certificate.issue_date.desc().nulls_last(), Certificate.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Certificate:
        import uuid
        cert = Certificate(
            id=str(uuid.uuid4()),
            user_id=data["user_id"],
            name=data["name"],
            issuer=data["issuer"],
            credential_id=data.get("credential_id"),
            credential_url=data.get("credential_url"),
            issue_date=data.get("issue_date"),
            expiry_date=data.get("expiry_date"),
            description=data.get("description"),
        )
        self.db.add(cert)
        await self.db.flush()
        return cert

    async def update(self, cert: Certificate, data: dict) -> Certificate:
        allowed = {
            "name", "issuer", "credential_id", "credential_url",
            "issue_date", "expiry_date", "description",
        }
        for key, value in data.items():
            if key in allowed:
                setattr(cert, key, value)
        cert.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return cert

    async def delete(self, certificate_id: str) -> bool:
        cert = await self.get_by_id(certificate_id)
        if not cert:
            return False
        await self.db.delete(cert)
        await self.db.flush()
        return True
