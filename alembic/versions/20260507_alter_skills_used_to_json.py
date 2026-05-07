"""alter_skills_used_to_json

Revision ID: auto_20260507
Revises: auto_202604291430
Create Date: 2026-05-07 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "auto_20260507"
down_revision = "auto_202604291430"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Change skills_used column from VARCHAR to JSON with data conversion."""
    # First, handle empty strings (convert to NULL)
    op.execute("""
        UPDATE experiences 
        SET skills_used = NULL 
        WHERE skills_used IS NOT NULL 
        AND (skills_used = '' OR skills_used = 'null')
    """)
    
    # Now alter column with USING clause for data conversion
    op.execute("""
        ALTER TABLE experiences 
        ALTER COLUMN skills_used TYPE JSON 
        USING CASE 
            WHEN skills_used IS NOT NULL 
            THEN skills_used::json 
            ELSE NULL 
        END
    """)


def downgrade() -> None:
    """Revert skills_used column from JSON to VARCHAR."""
    op.execute("""
        ALTER TABLE experiences 
        ALTER COLUMN skills_used TYPE VARCHAR(1000) 
        USING CASE 
            WHEN skills_used IS NOT NULL 
            THEN skills_used::text 
            ELSE NULL 
        END
    """)
