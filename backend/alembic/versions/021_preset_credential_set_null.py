"""Change output_presets.credential_id from CASCADE to SET NULL

Revision ID: 021
Revises: 020
Create Date: 2026-05-20

Before this migration presets were deleted cascade-style when their credential
was removed. That was surprising behaviour: deleting a credential could silently
wipe all presets configured under it, including their template references.

Now credential deletion simply NULLs the FK — the preset remains and the user
can reassign a different credential, or decide to delete the preset themselves.
"""

from alembic import op

# revision identifiers
revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing CASCADE FK constraint (PostgreSQL auto-names it this way)
    op.drop_constraint("output_presets_credential_id_fkey", "output_presets", type_="foreignkey")
    # Make the column nullable so PostgreSQL can set it to NULL on credential deletion
    op.alter_column("output_presets", "credential_id", nullable=True)
    # Re-create FK with SET NULL
    op.create_foreign_key(
        "output_presets_credential_id_fkey",
        "output_presets",
        "user_credentials",
        ["credential_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("output_presets_credential_id_fkey", "output_presets", type_="foreignkey")
    # NOTE: downgrade will fail if any presets currently have credential_id = NULL
    op.alter_column("output_presets", "credential_id", nullable=False)
    op.create_foreign_key(
        "output_presets_credential_id_fkey",
        "output_presets",
        "user_credentials",
        ["credential_id"],
        ["id"],
        ondelete="CASCADE",
    )
