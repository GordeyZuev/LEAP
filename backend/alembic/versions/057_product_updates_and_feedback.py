"""Product updates, confirmed email subscriptions, and feedback.

Revision ID: 057
Revises: 056
Create Date: 2026-10-03
"""

import json

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_updates",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("version", sa.String(32), nullable=True),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("audience_bullets", JSONB(), server_default="[]", nullable=False),
        sa.Column("creator_bullets", JSONB(), server_default="[]", nullable=False),
        sa.Column("audiences", JSONB(), server_default="[]", nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("newsletter_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("version", name="uq_product_updates_version"),
    )
    op.create_index("ix_product_updates_published", "product_updates", ["published_at"])

    history = [
        (
            "0.9.0.0",
            "A complete workflow for course video",
            "Bring recordings into LEAP and turn them into structured course materials, all in one place.",
            None,
        ),
        (
            "0.9.4",
            "Scheduled work you can rely on",
            "Safer account separation and background processing keep recurring video work moving predictably.",
            (2026, 2, 5),
        ),
        (
            "0.9.5",
            "Bring video in from more places",
            "Import recordings from popular platforms and Yandex Disk without changing your course workflow.",
            (2026, 2, 12),
        ),
        (
            "0.9.6",
            "Protect connected accounts",
            "Keep connected publishing accounts safer while you bring recordings and courses into LEAP.",
            (2026, 2, 17),
        ),
        (
            "0.9.6.1",
            "Rotate keys without service disruption",
            "Renew credential keys gradually while keeping existing account connections available.",
            (2026, 2, 19),
        ),
        (
            "0.9.6.2",
            "Build integrations with fewer surprises",
            "Clear request rules and configurable OAuth redirects make LEAP integrations easier to maintain.",
            (2026, 2, 23),
        ),
        (
            "0.9.6.3",
            "Prepare learner checks and reuse your data",
            "Add self-check questions to course materials and move recording data into tools your team already uses.",
            (2026, 3, 4),
        ),
        (
            "0.9.6.4",
            "Spend less time resolving source issues",
            "Consistent source access and language handling help video processing finish with fewer interruptions.",
            (2026, 3, 22),
        ),
        (
            "0.9.6.5",
            "Review publishing details before a run",
            "Check generated descriptions in advance and use your local timezone to avoid publishing surprises.",
            (2026, 4, 12),
        ),
        (
            "0.9.6.6",
            "Catch video file problems early",
            "Consistent format checks identify unsupported or mislabeled files before they disrupt processing.",
            (2026, 5, 11),
        ),
        (
            "0.9.7.0",
            "Reuse your setup and handle more formats",
            "Reuse workflows and process less common media without rebuilding settings or troubleshooting codecs.",
            (2026, 5, 20),
        ),
        (
            "0.10.0",
            "Build a repeatable video workflow",
            "Bring sources, templates, presets, and automation together to reduce setup for routine processing.",
            (2026, 5, 30),
        ),
        (
            "0.10.1",
            "Keep processing settings consistent",
            "Reuse processing settings across runs for predictable results without configuring everything again.",
            (2026, 6, 1),
        ),
        (
            "0.10.2",
            "Catch setup issues before processing",
            "Earlier checks make incomplete settings easier to fix before they interrupt a recording workflow.",
            (2026, 6, 2),
        ),
        (
            "0.10.3",
            "Prepare course details once and reuse them",
            "Reusable templates and presets reduce repeated editing when preparing course material for publication.",
            (2026, 6, 6),
        ),
        (
            "0.10.4",
            "Keep recording work on track",
            "Clearer source handling and background processing make long-running workflows easier to manage.",
            (2026, 6, 12),
        ),
        (
            "0.10.4.1",
            "Recover smoothly from interruptions",
            "Clearer recovery helps creators and viewers continue after a connection or processing job pauses.",
            (2026, 6, 14),
        ),
        (
            "0.10.4.2",
            "Make everyday work more dependable",
            "Small reliability fixes reduce interruptions across common LEAP workflows.",
            (2026, 6, 22),
        ),
        (
            "0.10.5.0",
            "See how accounts and quotas are used",
            "Usage and activity details help creators plan work and administrators resolve account issues sooner.",
            (2026, 7, 1),
        ),
        (
            "0.10.6.0",
            "Know what happened to each recording",
            "Clearer processing outcomes help creators decide what needs attention and what is ready to publish.",
            (2026, 7, 12),
        ),
        (
            "0.10.6.1",
            "Find recording status and files quickly",
            "A focused recording page puts the details creators need to review or fix a video within easy reach.",
            (2026, 8, 18),
        ),
        (
            "0.10.6.2",
            "Choose the right Yandex Disk folder",
            "Preview folders before import to avoid selecting the wrong source for course videos.",
            (2026, 8, 22),
        ),
        (
            "0.10.7.0",
            "Publish course material through LEAP",
            "Prepare shareable courses alongside video processing, with useful chapter navigation for viewers.",
            (2026, 8, 22),
        ),
        (
            "0.10.8.0",
            "Bring in MTS Link recordings and track reach",
            "Import sessions from another source and see whether shared recordings are reaching their audience.",
            (2026, 9, 3),
        ),
        (
            "0.10.8.1",
            "Give a playlist one course link",
            "A single public page helps viewers understand a course and move through its lectures in order.",
            (2026, 9, 5),
        ),
        (
            "0.10.8.2",
            "Help learners find the right lecture",
            "Useful course details and clearer navigation make a public catalog easier to browse and understand.",
            (2026, 9, 7),
        ),
        (
            "0.10.8.3",
            "Plan work with clearer usage and automation data",
            "Review activity over time and preview an automation run before committing resources to it.",
            (2026, 9, 9),
        ),
        (
            "0.10.9.0",
            "Give every lesson one clear viewing space",
            "Keep the video, its context, and learning materials together so viewers can focus on the lesson.",
            (2026, 9, 13),
        ),
        (
            "0.10.9.1",
            "Get to processing and playback sooner",
            "Faster lists and playback reduce waiting for creators managing recordings and viewers opening a lesson.",
            (2026, 9, 15),
        ),
        (
            "0.11.0.0",
            "Give a whole program one public home",
            "Bring related videos and courses together so viewers can explore a program from one link.",
            (2026, 9, 16),
        ),
        (
            "0.11.0.1",
            "Make access and automation easier to understand",
            "Clear statuses help creators manage work and viewers see which shared files are available to download.",
            (2026, 9, 16),
        ),
        (
            "0.11.0.2",
            "Keep processing steady through interruptions",
            "Automatic retries handle short slowdowns, while trimming preserves pauses inside a lecture.",
            (2026, 9, 20),
        ),
        (
            "0.11.1.0",
            "Keep courses and video imports moving",
            (
                "Spend less time finding the next task and recovering imports. Home shows activity; "
                "course folders keep lectures organized."
            ),
            (2026, 10, 2),
        ),
    ]
    release_notes = {
        "0.9.0.0": (
            [],
            [
                "Import recordings and prepare them for courses in LEAP.",
                "Create transcripts, subtitles, and topics with reusable templates.",
            ],
        ),
        "0.9.4": (
            [],
            [
                "Keep each user's data separate and schedule video processing.",
                "Speed up video processing and prepare the service for cloud storage.",
            ],
        ),
        "0.9.5": (
            [],
            [
                "Import videos from YouTube, VK, Rutube, and Yandex Disk.",
                "Sync a Yandex Disk folder or send processed videos to a publishing platform.",
            ],
        ),
        "0.9.6": (
            [],
            [
                "Encrypt credentials for connected Zoom, YouTube, and VK accounts.",
                "Rotate encryption keys and refine transcription vocabulary and topic controls.",
            ],
        ),
        "0.9.6.1": ([], ["Rotate credential keys in stages while keeping existing connections available."]),
        "0.9.6.2": ([], ["Set OAuth redirect addresses and validate API filters and processing options."]),
        "0.9.6.3": (
            [],
            ["Add self-check questions to course materials.", "Export recording data to JSON, CSV, or Excel."],
        ),
        "0.9.6.4": (
            [],
            ["Use browser cookies with supported video sources.", "Keep transcription and subtitle output in English."],
        ),
        "0.9.6.5": (
            [],
            [
                "Preview template-generated descriptions before publishing.",
                "Set your profile timezone for scheduled work.",
            ],
        ),
        "0.9.6.6": (
            [],
            [
                "Check the actual video format as well as its filename during import and upload.",
                "Keep downloaded filenames consistent with the source video.",
            ],
        ),
        "0.9.7.0": (
            [],
            [
                "Copy templates and automation jobs instead of rebuilding existing setup.",
                "Process less common WebM video formats and incomplete media more safely.",
            ],
        ),
        "0.10.0": (
            [],
            [
                "Save sources, templates, and presets for reuse in automated workflows.",
                "Run video processing with settings that are easier to review and repeat.",
            ],
        ),
        "0.10.1": ([], ["Reuse processing settings across runs for more consistent results."]),
        "0.10.2": ([], ["Find missing or invalid settings before processing starts."]),
        "0.10.3": ([], ["Reuse templates and presets instead of re-entering course publishing details."]),
        "0.10.4": (
            [],
            ["Manage recordings and sources consistently.", "Make background processing more reliable."],
        ),
        "0.10.4.1": (
            ["Resume public playback more reliably after temporary interruptions."],
            ["See clearer processing status when a job is interrupted."],
        ),
        "0.10.4.2": ([], ["Small improvements to reliability across everyday workflows."]),
        "0.10.5.0": (
            [],
            [
                "Review account usage and quota limits in one place.",
                "Small improvements to administration and video processing.",
            ],
        ),
        "0.10.6.0": ([], ["Review recording and automation results to see what needs attention."]),
        "0.10.6.1": ([], ["Find a recording's status, errors, and attached files more quickly."]),
        "0.10.6.2": ([], ["Preview Yandex Disk folders and choose a source in dialogs that fit the screen."]),
        "0.10.7.0": (
            ["Follow course chapters and topics beside the video while watching."],
            ["Add LEAP course publishing to a reusable processing template."],
        ),
        "0.10.8.0": (
            ["See how often public recordings are viewed and downloaded."],
            ["Import recordings from MTS Link."],
        ),
        "0.10.8.1": (
            ["Browse the course and its lectures on a mobile-friendly public page."],
            ["Publish a playlist with one course link and preview video details before adding them."],
        ),
        "0.10.8.2": (
            ["Use course details to find and navigate public lectures."],
            ["Format course descriptions and reuse publishing details across recordings."],
        ),
        "0.10.8.3": (
            ["See age guidance before opening public learning materials."],
            ["Review usage over a chosen period and preview which recordings automation would process."],
        ),
        "0.10.9.0": (
            [
                "Watch a recording or course with its chapters, summary, questions, and files in one place.",
                "Continue to the next course video when one is available.",
            ],
            ["Reconnect expired platform accounts and edit generated lecture content."],
        ),
        "0.10.9.1": (
            ["Start playback sooner on public recording and course pages."],
            ["Load creator lists faster and retry missing lecture topics without rerunning all processing."],
        ),
        "0.11.0.0": (
            ["Search and sort a program's videos and courses in either a grid or a list."],
            ["Collect selected videos and courses under one shareable channel link."],
        ),
        "0.11.0.1": (
            ["See when downloads are disabled and why a shared file cannot be saved."],
            ["Use clearer automation statuses, sharing controls, and delete confirmations."],
        ),
        "0.11.0.2": (
            [],
            [
                "Retry short MTS Link and VK slowdowns automatically.",
                "Preserve pauses in the middle of a lecture while trimming silence at the end.",
            ],
        ),
        "0.11.1.0": (
            [
                "Return from a lecture to its folder in the course.",
                "Continue from the same point if a temporary video link needs to refresh.",
                "Match public pages to your device's light or dark theme.",
            ],
            [
                "See recent recordings and processing status on Home to know what needs attention.",
                "Group course lectures into folders to keep programs organized.",
                "Import videos from files, links, or playlists; resume file uploads after an interruption.",
                "Choose the available video quality before importing a link.",
            ],
        ),
    }

    def sql_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    for index, (version, title, summary, release_date) in enumerate(history, start=1):
        audience_bullets, creator_bullets = release_notes.get(version, ([], []))
        release_date_sql = (
            sql_literal(f"{release_date[0]:04d}-{release_date[1]:02d}-{release_date[2]:02d}")
            if release_date
            else "NULL"
        )
        audience_json = sql_literal(json.dumps(audience_bullets, ensure_ascii=False)) + "::jsonb"
        creator_json = sql_literal(json.dumps(creator_bullets, ensure_ascii=False)) + "::jsonb"
        op.execute(
            f"""
            INSERT INTO product_updates (
                id, version, title, summary, audience_bullets, creator_bullets, audiences,
                is_published, newsletter_enabled, release_date, created_at, updated_at, published_at
            ) VALUES (
                {sql_literal(f"{index:026d}")}, {sql_literal(version)}, {sql_literal(title)}, {sql_literal(summary)},
                {audience_json}, {creator_json}, '[]'::jsonb,
                TRUE, FALSE, {release_date_sql}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )

    op.create_table(
        "product_news_subscriptions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("interests", JSONB(), server_default="[]", nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("confirmation_token_hash", sa.String(64), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_product_news_subscriptions_email"),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'unsubscribed')", name="ck_product_news_subscription_status"
        ),
    )
    op.create_index("ix_product_news_subscriptions_status", "product_news_subscriptions", ["status"])

    op.create_table(
        "product_update_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("update_id", sa.String(26), sa.ForeignKey("product_updates.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "subscription_id",
            sa.String(26),
            sa.ForeignKey("product_news_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("update_id", "subscription_id", name="uq_product_update_delivery_recipient"),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'skipped')", name="ck_product_update_delivery_status"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_product_update_delivery_attempts"),
    )
    op.create_index("ix_product_update_deliveries_status", "product_update_deliveries", ["status"])

    op.create_table(
        "product_feedback",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("interests", JSONB(), server_default="[]", nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("reply_email", sa.String(320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('idea', 'problem', 'question', 'other')", name="ck_product_feedback_kind"),
    )
    op.create_index("ix_product_feedback_created", "product_feedback", ["created_at"])

    # Grafana receives aggregates only. Subscriber addresses, tokens, and feedback text
    # remain inaccessible to its read-only role.
    op.execute(
        """
        CREATE VIEW product_communications_current_stats WITH (security_barrier = true) AS
        SELECT 'subscription_status'::text AS metric, status::text AS dimension, count(*)::bigint AS value
        FROM product_news_subscriptions GROUP BY status
        UNION ALL
        SELECT 'subscription_interest'::text, interest.value, count(*)::bigint
        FROM product_news_subscriptions s
        CROSS JOIN LATERAL jsonb_array_elements_text(s.interests) AS interest(value)
        WHERE s.status = 'confirmed'
        GROUP BY interest.value
        UNION ALL
        SELECT 'feedback_kind'::text, kind::text, count(*)::bigint
        FROM product_feedback GROUP BY kind
        UNION ALL
        SELECT 'feedback_interest'::text, interest.value, count(*)::bigint
        FROM product_feedback f
        CROSS JOIN LATERAL jsonb_array_elements_text(f.interests) AS interest(value)
        GROUP BY interest.value
        UNION ALL
        SELECT 'delivery_status'::text, status::text, count(*)::bigint
        FROM product_update_deliveries GROUP BY status;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
            GRANT SELECT ON product_communications_current_stats TO grafana_ro;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS product_communications_current_stats")
    op.drop_index("ix_product_feedback_created", table_name="product_feedback")
    op.drop_table("product_feedback")
    op.drop_index("ix_product_update_deliveries_status", table_name="product_update_deliveries")
    op.drop_table("product_update_deliveries")
    op.drop_index("ix_product_news_subscriptions_status", table_name="product_news_subscriptions")
    op.drop_table("product_news_subscriptions")
    op.drop_index("ix_product_updates_published", table_name="product_updates")
    op.drop_table("product_updates")
