"""Merge embedding 768 migration with main branch

Revision ID: b2c3d4e5f678
Revises: a1b2c3d4e567, 35d5958cfe86
Create Date: 2026-04-25

"""
from typing import Sequence, Union


revision: str = "b2c3d4e5f678"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e567", "35d5958cfe86")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass