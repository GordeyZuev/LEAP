"""Update processing stage types enum

Revision ID: 004
Revises: 003
Create Date: 2026-01-23 14:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL doesn't support ALTER TYPE directly with enum values
    # We need to:
    # 1. Create a new enum type
    # 2. Alter the column to use the new type
    # 3. Drop the old type

    # First, create the new enum type with correct values
    op.execute(
        """
        CREATE TYPE processingstagetype_new AS ENUM (
            'TRANSCRIBE',
            'EXTRACT_TOPICS',
            'GENERATE_SUBTITLES'
        )
        """
    )

    # Alter the column to use the new type with a mapping
    # Map old values to new values where they exist
    op.execute(
        """
        ALTER TABLE processing_stages
        ALTER COLUMN stage_type TYPE processingstagetype_new
        USING (
            CASE stage_type::text
                WHEN 'TRANSCRIPTION' THEN 'TRANSCRIBE'::processingstagetype_new
                WHEN 'TOPIC_EXTRACTION' THEN 'EXTRACT_TOPICS'::processingstagetype_new
                ELSE NULL::processingstagetype_new
            END
        )
        """
    )

    # Drop the old enum type
    op.execute("DROP TYPE processingstagetype")

    # Rename the new type to the original name
    op.execute("ALTER TYPE processingstagetype_new RENAME TO processingstagetype")


def downgrade() -> None:
    # Reverse the process
    # Create old enum type
    op.execute(
        """
        CREATE TYPE processingstagetype_old AS ENUM (
            'DOWNLOAD',
            'VIDEO_PROCESSING',
            'TRANSCRIPTION',
            'TOPIC_EXTRACTION',
            'UPLOAD'
        )
        """
    )

    # Alter the column back to old type
    op.execute(
        """
        ALTER TABLE processing_stages
        ALTER COLUMN stage_type TYPE processingstagetype_old
        USING (
            CASE stage_type::text
                WHEN 'TRANSCRIBE' THEN 'TRANSCRIPTION'::processingstagetype_old
                WHEN 'EXTRACT_TOPICS' THEN 'TOPIC_EXTRACTION'::processingstagetype_old
                ELSE NULL::processingstagetype_old
            END
        )
        """
    )

    # Drop the new enum type
    op.execute("DROP TYPE processingstagetype")

    # Rename old type back to original name
    op.execute("ALTER TYPE processingstagetype_old RENAME TO processingstagetype")
