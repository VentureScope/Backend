"""Extend organization fields

Revision ID: o8j2k5l6m7n8
Revises: n7i1j4k5l6m7
Create Date: 2026-05-23

Adds:
  organizations:
    - twitter_url, tech_stacks, products
    - headquarters, founded_year, company_size
    - contact_email, contact_phone, mission_statement
    - custom_fields

  organization_members:
    - job_title

  organization_invites:
    - team_role
"""

from alembic import op
import sqlalchemy as sa

revision = "o8j2k5l6m7n8"
down_revision = "n7i1j4k5l6m7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # organizations — extended profile fields
    # ------------------------------------------------------------------
    op.add_column("organizations", sa.Column("twitter_url", sa.String(500), nullable=True))
    op.add_column("organizations", sa.Column("tech_stacks", sa.JSON, nullable=True))
    op.add_column("organizations", sa.Column("products", sa.JSON, nullable=True))
    op.add_column("organizations", sa.Column("headquarters", sa.String(255), nullable=True))
    op.add_column("organizations", sa.Column("founded_year", sa.Integer, nullable=True))
    op.add_column("organizations", sa.Column("company_size", sa.String(50), nullable=True))
    op.add_column("organizations", sa.Column("contact_email", sa.String(255), nullable=True))
    op.add_column("organizations", sa.Column("contact_phone", sa.String(50), nullable=True))
    op.add_column("organizations", sa.Column("mission_statement", sa.Text, nullable=True))
    op.add_column("organizations", sa.Column("custom_fields", sa.JSON, nullable=True))

    # ------------------------------------------------------------------
    # organization_members — job/team title
    # ------------------------------------------------------------------
    op.add_column("organization_members", sa.Column("job_title", sa.String(255), nullable=True))

    # ------------------------------------------------------------------
    # organization_invites — team_role (free-text job title at invite time)
    # ------------------------------------------------------------------
    op.add_column("organization_invites", sa.Column("team_role", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("organization_invites", "team_role")
    op.drop_column("organization_members", "job_title")

    for col in [
        "custom_fields", "mission_statement", "contact_phone", "contact_email",
        "company_size", "founded_year", "headquarters",
        "products", "tech_stacks", "twitter_url",
    ]:
        op.drop_column("organizations", col)
