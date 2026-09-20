# Product news, email subscriptions, and feedback

LEAP's **News & Release Notes from LEAP** page (`/updates`) is the public archive for notable product changes. It shows the five newest entries first; older entries appear below with a fade and expand control. Each release is formatted as bullet points. Signed-in users see **News & Updates** in the application sidebar, public viewers see a compact **News & Updates** link beside the theme and **Copy link** controls, and the sign-in release modal uses the latest published entry. The archive, modal, and email use the same published update records.

## Publishing an update

Administrators open **Admin → News & feedback** (`/admin/updates`). The page is divided into **News & email** and **Feedback** sections using the same tab control as Settings. Create or edit a draft with a title, short plain-text note, audience and creator bullets (one item per line), optional version, and the interests it concerns:

- `viewers` — watching materials;
- `course_publishing` — publishing courses;
- `video_processing` — processing video.

Publishing makes the update visible in the public archive and eligible for the news strip. Publishing never sends email. Email also requires the draft's explicit newsletter setting, a second administrator action, and a review of the confirmed recipient count. An empty update audience targets all confirmed subscribers; a selected audience matches subscribers who selected **any** of those interests. Keep updates focused on notable user-visible changes.

Migration 057 creates the feature tables and seeds the archive from `0.9.0.0` once. Future updates are created and published in Admin; they do not need a migration or frontend code edit. Historical entries are archive-only and have email disabled. The `0.9.0.0` entry has no date or retrospective paragraph.

## Visitor subscription and feedback

The email form is on `/updates/subscribe`, separate from the archive and feedback, and does not require a LEAP account. A visitor selects at least one interest and confirms their address through a single-use email link. Confirmation links expire after 24 hours. Existing confirmed subscriptions are not silently changed by a second public form submission. A signed email link lets a subscriber change interests or unsubscribe; opening it alone does not change the subscription.

Feedback has its own page at `/updates/feedback`. It requires one or more interests, a kind, and a message; a reply address is optional. Admin can review the submitted text and optional reply address. These are personal data: do not copy them into dashboards, logs, or exports without a separate need and access review.

## Email delivery and operations

Email is sent only when `EMAIL_ENABLED`, SMTP host, username, password, sender address, and a public HTTPS `EMAIL_BASE_URL` are configured. Product-news email is disabled for localhost and private IP addresses so confirmation and unsubscribe links cannot point at the administrator's machine. Confirmation send failures return an error so a visitor can try again. Newsletters include the update note and both audience/creator bullet lists, plus a link to the public release entry. The shared email layout uses the LEAP symbol from the public frontend URL. Newsletters are snapshotted into per-recipient delivery rows and queued through the Celery `async_operations` queue after the database commit. Delivery is batched; Admin shows pending, sent, failed, and skipped outcomes. A retry resets failed rows and stale in-progress rows for delivery. SMTP acceptance is recorded as `sent`; it does not prove delivery to an inbox.

The per-update unique constraint prevents creating a second delivery row for the same subscriber and update. Queueing is idempotent at the database level. Check that API and Celery workers both run code containing the task before enabling the newsletter action. Keep SMTP logs and error messages free of recipient addresses and message content.

SMTP delivery is at-least-once when a worker stops after the mail server accepts a message but before LEAP records success. Retrying a stale `sending` row can therefore send a duplicate in that rare failure window. The Admin label “accepted by SMTP” describes the recorded SMTP handoff, not inbox placement or exactly-once delivery.

## Analytics and privacy

Admin shows current subscription counts and interest distribution, newsletter delivery states, and feedback counts by kind and interest. Admin feedback review is the only interface here that exposes feedback text and reply email.

Grafana's `grafana_ro` role receives `SELECT` on `product_communications_current_stats` only. The view exposes aggregate metric, dimension, and value rows; it contains no email addresses, subscription IDs, feedback text, or reply addresses. Do not grant this role access to the underlying communication tables. The aggregate view represents current totals, not historical time series.

## API surface

Public endpoints:

- `GET /api/v1/product-updates`
- `POST /api/v1/product-news/subscribe`
- `POST /api/v1/product-news/confirm`
- `POST /api/v1/product-news/unsubscribe`
- `POST /api/v1/product-news/preferences/validate`
- `PUT /api/v1/product-news/preferences`
- `POST /api/v1/product-feedback`

Public pages: `/updates`, `/updates/subscribe`, and `/updates/feedback`.

Admin endpoints are under `/api/v1/admin/product-updates`, `/api/v1/admin/product-news`, and `/api/v1/admin/product-feedback`; all require administrator authentication.

- `GET /api/v1/admin/product-news/stats`
- `GET /api/v1/admin/product-news/audience-count`
- `GET /api/v1/admin/product-feedback`
- `GET`, `POST /api/v1/admin/product-updates`
- `PATCH`, `DELETE /api/v1/admin/product-updates/{update_id}`
- `POST /api/v1/admin/product-updates/{update_id}/publish`, `/send`, and `/retry`

## Deployment

Apply Alembic migration **057** before or with the API release. Deploy API and Celery workers before exposing frontend actions that publish or queue email. Set the public frontend URL used by the email service and configure SMTP before testing confirmation or newsletter delivery. Grafana grants are applied by migration 057 when the `grafana_ro` role already exists; if that role is provisioned later, grant it `SELECT` on the aggregate view explicitly.
