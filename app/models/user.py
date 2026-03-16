"""
AccountBase-equivalent: core user identity and auth (Data Dictionary).
"""
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
import uuid
import enum

from app.core.database import Base


class UserRole(str, enum.Enum):
    STUDENT = "student"
    PROFESSIONAL = "professional"
    B2B_CLIENT = "b2b_client"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    career_interest: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.PROFESSIONAL.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
