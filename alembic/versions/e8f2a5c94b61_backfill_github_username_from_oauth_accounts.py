"""Backfill github_username from OAuth accounts

Revision ID: e8f2a5c94b61
Revises: d7f1b2c93e47
Create Date: 2026-04-05

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import json

# revision identifiers, used by Alembic
revision: str = "e8f2a5c94b61"
down_revision: Union[str, None] = "d7f1b2c93e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill github_username field for existing GitHub OAuth users."""

    # Get database connection
    connection = op.get_bind()

    # Query to find all GitHub OAuth accounts with provider_data containing login information
    result = connection.execute(
        sa.text("""
            SELECT oa.user_id, oa.provider_data
            FROM oauth_accounts oa
            JOIN users u ON oa.user_id = u.id
            WHERE oa.provider = 'github'
            AND u.github_username IS NULL
            AND oa.provider_data IS NOT NULL
        """)
    )

    # Process each GitHub OAuth account
    for row in result:
        user_id, provider_data_json = row

        if provider_data_json:
            try:
                provider_data = json.loads(provider_data_json)
                github_username = provider_data.get("provider_login")

                if github_username:
                    # Update the user's github_username field
                    connection.execute(
                        sa.text("""
                            UPDATE users 
                            SET github_username = :github_username, updated_at = CURRENT_TIMESTAMP
                            WHERE id = :user_id
                        """),
                        {"github_username": github_username, "user_id": user_id},
                    )

            except (json.JSONDecodeError, KeyError):
                # Skip invalid JSON or missing data
                continue


def downgrade() -> None:
    """
    Reverse the migration by clearing github_username for OAuth users.
    Note: This only clears for users who have GitHub OAuth accounts.
    """

    connection = op.get_bind()

    # Clear github_username for users who have GitHub OAuth accounts
    connection.execute(
        sa.text("""
            UPDATE users 
            SET github_username = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id IN (
                SELECT DISTINCT user_id 
                FROM oauth_accounts 
                WHERE provider = 'github'
            )
        """)
    )
