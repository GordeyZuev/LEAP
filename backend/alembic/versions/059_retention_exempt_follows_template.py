"""Let recordings follow the template retention flag.

Revision ID: 059
Revises: 058
Create Date: 2026-10-05

``retention_exempt`` NULL means the recording follows its template. True and
false are overrides. Existing ``false`` values become NULL so a later template
edit applies. Existing ``true`` stays an override, so a recording that was
explicitly kept is not put back on the schedule.
"""

import sqlalchemy as sa

from alembic import op

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("recordings", "retention_exempt", server_default=None)
    op.alter_column("recordings", "retention_exempt", existing_type=sa.Boolean(), nullable=True)
    op.execute("UPDATE recordings SET retention_exempt = NULL WHERE retention_exempt = false")


def downgrade() -> None:
    op.execute("UPDATE recordings SET retention_exempt = false WHERE retention_exempt IS NULL")
    op.alter_column(
        "recordings",
        "retention_exempt",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )
