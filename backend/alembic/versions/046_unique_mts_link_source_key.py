"""Delete empty MTS Link duplicate rows and unique (user_id, source_key)

Revision ID: 046
Revises: 045
Create Date: 2026-09-07

Hard-deletes extra MTS rows that have no storage keys and are not in-flight.
CASCADE drops source_metadata, playlist items, stages. Does not call storage.
Losers with media keys or an active pipeline abort the upgrade.
"""

from sqlalchemy import bindparam, text

from alembic import op

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None

_HAS_MEDIA = """
(
  NULLIF(BTRIM(r.local_video_path), '') IS NOT NULL
  OR NULLIF(BTRIM(r.processed_video_path), '') IS NOT NULL
  OR NULLIF(BTRIM(r.processed_audio_path), '') IS NOT NULL
  OR NULLIF(BTRIM(r.transcription_dir), '') IS NOT NULL
)
"""

_STATUS_RANK = """
CASE r.status::text
  WHEN 'READY' THEN 100
  WHEN 'UPLOADED' THEN 90
  WHEN 'PROCESSED' THEN 80
  WHEN 'UPLOADING' THEN 70
  WHEN 'PROCESSING' THEN 60
  WHEN 'DOWNLOADED' THEN 50
  WHEN 'DOWNLOADING' THEN 40
  WHEN 'INITIALIZED' THEN 30
  WHEN 'PENDING_CONVERSION' THEN 20
  WHEN 'PENDING_SOURCE' THEN 15
  WHEN 'SKIPPED' THEN 10
  WHEN 'EXPIRED' THEN 0
  ELSE 5
END
"""

_IN_FLIGHT = frozenset({"DOWNLOADING", "PROCESSING", "UPLOADING"})


def _dup_groups(conn):
    return conn.execute(
        text(
            """
            SELECT sm.user_id, sm.source_key
            FROM source_metadata sm
            JOIN recordings r ON r.id = sm.recording_id
            WHERE sm.source_type = 'MTS_LINK'
            GROUP BY sm.user_id, sm.source_key
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()


def _group_rows(conn, user_id, source_key):
    return conn.execute(
        text(
            f"""
            SELECT r.id,
                   {_HAS_MEDIA} AS has_media,
                   r.on_air,
                   r.pipeline_task_id,
                   r.status::text AS status
            FROM source_metadata sm
            JOIN recordings r ON r.id = sm.recording_id
            WHERE sm.source_type = 'MTS_LINK'
              AND sm.user_id IS NOT DISTINCT FROM :user_id
              AND sm.source_key = :source_key
            ORDER BY
              ({_HAS_MEDIA}) DESC,
              {_STATUS_RANK} DESC,
              r.id ASC
            """
        ),
        {"user_id": user_id, "source_key": source_key},
    ).fetchall()


def upgrade() -> None:
    conn = op.get_bind()
    to_delete: list[int] = []
    blocked: list[int] = []

    for user_id, source_key in _dup_groups(conn):
        rows = _group_rows(conn, user_id, source_key)
        for rec_id, has_media, on_air, pipeline_task_id, status in rows[1:]:
            if has_media or on_air or pipeline_task_id or status in _IN_FLIGHT:
                blocked.append(int(rec_id))
            else:
                to_delete.append(int(rec_id))

    if blocked:
        raise RuntimeError(
            "MTS Link duplicate rows have media keys or an in-flight pipeline; "
            f"refusing to delete recording ids {blocked}"
        )

    if to_delete:
        conn.execute(
            text("DELETE FROM recordings WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": to_delete},
        )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_source_metadata_mts_user_key
        ON source_metadata (user_id, source_key)
        WHERE source_type = 'MTS_LINK'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_source_metadata_mts_user_key")
