"""Rename ml_training_runs.staging_pkl_key to staging_forecast_key

Revision ID: x7s1t4u5v6w7
Revises: w6r0s3t4u5v6
Create Date: 2026-06-03

The pipeline no longer produces or deploys model .pkl files — inference is
driven entirely by the forecast CSVs. The column was already being reused to
store the forecast CSV path; this migration renames it to match its actual
purpose.

Uses IF EXISTS / IF NOT EXISTS guards so it is safe to run against databases
that may have been partially migrated by the raw schema.sql.
"""

from alembic import op

revision: str = "x7s1t4u5v6w7"
down_revision: str = "w6r0s3t4u5v6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename only if the old column still exists and the new one does not yet.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ml_training_runs'
                  AND column_name = 'staging_pkl_key'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ml_training_runs'
                  AND column_name = 'staging_forecast_key'
            ) THEN
                ALTER TABLE ml_training_runs
                    RENAME COLUMN staging_pkl_key TO staging_forecast_key;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ml_training_runs'
                  AND column_name = 'staging_forecast_key'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ml_training_runs'
                  AND column_name = 'staging_pkl_key'
            ) THEN
                ALTER TABLE ml_training_runs
                    RENAME COLUMN staging_forecast_key TO staging_pkl_key;
            END IF;
        END $$;
        """
    )
