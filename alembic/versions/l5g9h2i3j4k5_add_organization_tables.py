"""Add organization tables

Revision ID: l5g9h2i3j4k5
Revises: a4d383b18d2e
Create Date: 2026-05-20

Creates:
  - organizations
  - organization_members
  - organization_invites
  - organization_roadmaps
"""

from alembic import op
import sqlalchemy as sa

revision = "l5g9h2i3j4k5"
down_revision = "a4d383b18d2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # organizations
    # ------------------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("legal_name", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("tagline", sa.String(500), nullable=True),
        sa.Column("logo_url", sa.String(1000), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("core_services", sa.JSON, nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("github_orgs", sa.JSON, nullable=True),
        sa.Column("github_repos", sa.JSON, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_organizations_owner_id", "organizations", ["owner_id"])

    # ------------------------------------------------------------------
    # organization_members
    # ------------------------------------------------------------------
    op.create_table(
        "organization_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )
    op.create_index("ix_org_members_organization_id", "organization_members", ["organization_id"])
    op.create_index("ix_org_members_user_id", "organization_members", ["user_id"])

    # ------------------------------------------------------------------
    # organization_invites
    # ------------------------------------------------------------------
    op.create_table(
        "organization_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_by", sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_org_invite_token", "organization_invites", ["token"], unique=True)
    op.create_index("ix_org_invite_email", "organization_invites", ["email"])
    op.create_index("ix_org_invite_organization_id", "organization_invites", ["organization_id"])

    # ------------------------------------------------------------------
    # organization_roadmaps
    # ------------------------------------------------------------------
    op.create_table(
        "organization_roadmaps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "roadmap_id", sa.String(36),
            sa.ForeignKey("learning_roadmaps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by", sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("organization_id", "roadmap_id", name="uq_org_roadmap"),
    )
    op.create_index("ix_org_roadmaps_organization_id", "organization_roadmaps", ["organization_id"])
    op.create_index("ix_org_roadmaps_roadmap_id", "organization_roadmaps", ["roadmap_id"])


def downgrade() -> None:
    op.drop_table("organization_roadmaps")
    op.drop_table("organization_invites")
    op.drop_table("organization_members")
    op.drop_table("organizations")
