"""
Certificate management service.
"""

from app.models.certificate import Certificate
from app.repositories.certificate_repository import CertificateRepository
from app.schemas.certificate import CertificateCreate, CertificateUpdate


class CertificateService:
    def __init__(self, db):
        self.db = db
        self.repo = CertificateRepository(db)

    async def get_all_for_user(self, user_id: str) -> list[Certificate]:
        return await self.repo.get_by_user(user_id)

    async def create_certificate(
        self, user_id: str, data: CertificateCreate
    ) -> Certificate:
        cert_data = data.model_dump()
        cert_data["user_id"] = user_id
        cert = await self.repo.create(cert_data)
        await self.db.commit()
        return cert

    async def update_certificate(
        self, certificate_id: str, user_id: str, data: CertificateUpdate
    ) -> Certificate | None:
        cert = await self.repo.get_by_id(certificate_id)
        if not cert or cert.user_id != user_id:
            return None

        update_data = data.model_dump(exclude_unset=True)
        cert = await self.repo.update(cert, update_data)
        await self.db.commit()
        return cert

    async def delete_certificate(
        self, certificate_id: str, user_id: str
    ) -> bool:
        cert = await self.repo.get_by_id(certificate_id)
        if not cert or cert.user_id != user_id:
            return False

        success = await self.repo.delete(certificate_id)
        if success:
            await self.db.commit()
        return success
