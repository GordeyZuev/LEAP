"""Add final_duration, change duration to Float, unify all durations to seconds

Revision ID: 016
Revises: 015
Create Date: 2026-02-16

- Add final_duration (Float) for tracking transcription audio duration (seconds).
- Change duration column from Integer to Float for sub-second precision.
- Convert existing Zoom recordings duration from minutes to seconds.
  (yt-dlp sources already store seconds; LOCAL_FILE/YANDEX_DISK store 0.)
"""

import sqlalchemy as sa

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add final_duration column
    op.add_column("recordings", sa.Column("final_duration", sa.Float(), nullable=True))

    # 2. Change duration from Integer to Float
    op.alter_column(
        "recordings",
        "duration",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="duration::double precision",
    )

    # 3. Convert Zoom recordings: minutes → seconds
    #    Zoom recordings are identified via source_metadata.source_type = 'ZOOM'
    op.execute(
        """
        UPDATE recordings
        SET duration = duration * 60
        WHERE id IN (
            SELECT recording_id FROM source_metadata WHERE source_type = 'ZOOM'
        )
        AND duration > 0
        """
    )


def downgrade() -> None:
    # Revert Zoom durations: seconds → minutes
    op.execute(
        """
        UPDATE recordings
        SET duration = duration / 60
        WHERE id IN (
            SELECT recording_id FROM source_metadata WHERE source_type = 'ZOOM'
        )
        AND duration > 0
        """
    )

    # Revert duration column type
    op.alter_column(
        "recordings",
        "duration",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="duration::integer",
    )

    # Drop final_duration
    op.drop_column("recordings", "final_duration")
