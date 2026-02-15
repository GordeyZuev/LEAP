"""Add uniqueness constraints for templates, presets, automation jobs, and credentials

Revision ID: 015
Revises: 014
Create Date: 2026-02-15

Data cleanup: auto-resolve existing duplicates by appending (2), (3) etc. to duplicate
names before adding constraints. This ensures the migration succeeds even with current
duplicates in production.

Constraints added:
- recording_templates: UNIQUE (user_id, name)
- output_presets: UNIQUE (user_id, name)
- automation_jobs: UNIQUE (user_id, name)
- user_credentials: UNIQUE (user_id, platform, account_name)
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def _deduplicate_by_name(connection, table_name, group_cols):
    """
    Resolve duplicate names by appending (2), (3), etc. to later entries.

    Args:
        connection: DB connection
        table_name: Table to clean up
        group_cols: Columns that form the uniqueness group (e.g. ['user_id', 'name'])
    """
    group_expr = ", ".join(group_cols)
    # Find groups that have duplicates (table/column names are hardcoded, not user input)
    dup_sql = f"SELECT {group_expr}, COUNT(*) as cnt FROM {table_name} GROUP BY {group_expr} HAVING COUNT(*) > 1"  # noqa: S608
    dup_query = sa.text(dup_sql)
    duplicates = connection.execute(dup_query).fetchall()

    if not duplicates:
        return

    for dup_row in duplicates:
        # Build WHERE clause for this duplicate group
        where_parts = []
        params = {}
        for i, col in enumerate(group_cols):
            val = dup_row[i]
            if val is None:
                where_parts.append(f"{col} IS NULL")
            else:
                where_parts.append(f"{col} = :val_{i}")
                params[f"val_{i}"] = val
        where_clause = " AND ".join(where_parts)

        # Get all rows in this duplicate group, ordered by id (keep first, rename rest)
        rows_sql = f"SELECT id, name FROM {table_name} WHERE {where_clause} ORDER BY id ASC"  # noqa: S608
        rows_query = sa.text(rows_sql)
        rows = connection.execute(rows_query, params).fetchall()

        # Skip the first row (original), rename the rest
        for seq, row in enumerate(rows[1:], start=2):
            row_id = row[0]
            original_name = row[1]
            new_name = f"{original_name} ({seq})"
            connection.execute(
                sa.text(f"UPDATE {table_name} SET name = :new_name WHERE id = :id"),  # noqa: S608
                {"new_name": new_name, "id": row_id},
            )


def upgrade() -> None:
    conn = op.get_bind()

    # --- Data cleanup: resolve duplicates before adding constraints ---

    # 1. recording_templates: deduplicate by (user_id, name)
    _deduplicate_by_name(conn, "recording_templates", ["user_id", "name"])

    # 2. output_presets: deduplicate by (user_id, name)
    _deduplicate_by_name(conn, "output_presets", ["user_id", "name"])

    # 3. automation_jobs: deduplicate by (user_id, name)
    _deduplicate_by_name(conn, "automation_jobs", ["user_id", "name"])

    # 4. user_credentials: deduplicate by (user_id, platform, account_name)
    _deduplicate_by_name(conn, "user_credentials", ["user_id", "platform", "account_name"])

    # --- Add unique constraints ---

    op.create_unique_constraint(
        "uq_templates_user_name",
        "recording_templates",
        ["user_id", "name"],
    )

    op.create_unique_constraint(
        "uq_presets_user_name",
        "output_presets",
        ["user_id", "name"],
    )

    op.create_unique_constraint(
        "uq_automation_jobs_user_name",
        "automation_jobs",
        ["user_id", "name"],
    )

    op.create_unique_constraint(
        "uq_credentials_user_platform_account",
        "user_credentials",
        ["user_id", "platform", "account_name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_credentials_user_platform_account", "user_credentials", type_="unique")
    op.drop_constraint("uq_automation_jobs_user_name", "automation_jobs", type_="unique")
    op.drop_constraint("uq_presets_user_name", "output_presets", type_="unique")
    op.drop_constraint("uq_templates_user_name", "recording_templates", type_="unique")
