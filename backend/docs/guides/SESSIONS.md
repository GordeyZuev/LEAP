# Sessions & Token Version

This guide documents the session-revocation primitive (`users.token_version`),
how the active-sessions UI maps onto `refresh_tokens`, and how to use these
mechanisms during a security incident.

## Why token_version

Access tokens are stateless JWTs valid until their `exp` (default 30 min).
Before v0.10.1, `POST /auth/logout-all` only revoked refresh tokens — the
already-issued access JWT on another device kept working until it expired.
For a security-incident scenario (stolen device, leaked token) that lag is
unacceptable.

`users.token_version` is an integer counter persisted on the user row and
embedded into every JWT as the `tv` claim. `get_current_user` already loads
the user row to check `is_active`, so adding `payload["tv"] == user.token_version`
is free in terms of latency. Bumping the counter invalidates every live JWT
for that user instantly.

## What bumps token_version

| Trigger | Endpoint | Effect |
|---|---|---|
| User clicks "Log out all devices" | `POST /api/v1/auth/logout-all` | Bump + revoke all refresh rows + clear current cookies. |
| User clicks "Log out other devices" | `POST /api/v1/auth/logout-others` | Bump + revoke all refresh rows + immediately mint a fresh pair for the caller. |
| User changes password | `POST /api/v1/users/me/password` | Bump + revoke all refresh rows. UI redirects to `/login`. |

`DELETE /api/v1/auth/sessions/{id}` does **NOT** bump `token_version` — it
revokes a single refresh row, so the targeted device dies on its next
refresh attempt (within `SECURITY_JWT_ACCESS_TOKEN_EXPIRE_MINUTES`). For
instant per-device kill, use `/logout-all`.

## Active-sessions UI surface

Settings → **Active sessions** lists every refresh-token row that is
non-revoked and non-expired for the caller. Each row carries:

- `device_label` — derived heuristically from the User-Agent
  (`Chrome · macOS`, `Safari · iOS`, …). See `api/auth/device.py`.
- `last_used_at` — updated on every successful `/auth/refresh`.
- `is_current` — true when the row's refresh token matches the refresh
  cookie on the current request.
- `ip_hash` — `sha256(jwt_secret_key || raw_ip)`. **Raw client IPs are never
  persisted** (see [CREDENTIAL_SECURITY.md](CREDENTIAL_SECURITY.md)).

## Incident response — invalidate a user from the database

If a user reports a compromised account and you can't have them log in to
click the button, bump the counter directly:

```sql
UPDATE users SET token_version = token_version + 1 WHERE email = '<email>';
```

Next request from any of their devices fails with 401, and the frontend's
refresh interceptor bounces them to `/login`. No deploy required, no Redis
state to flush.

## Deploy note

Existing access tokens minted before migration 022 do not carry the `tv`
claim. `get_current_user` reads `payload.get("tv")` (→ `None`) and compares
it to `user.token_version` (→ `0` from the migration default). They mismatch,
so **every active session is invalidated by the first deploy** of v0.10.1.
Users will re-login once. Refresh cookies stay valid for the user agent —
the auto-refresh interceptor swaps to a new pair — but the `tv` mismatch
fires on the new refresh too, so the next request through the cookie path
also forces a re-login. This is the intended behaviour and is
non-destructive.

## Why no Redis blacklist

A jti-based blacklist would allow instant revocation of a *specific* access
token without nuking the user's other sessions. We don't need this today:

- `logout-all` and password-change are the common "instant" cases — solved
  by `token_version` without new infra.
- Per-device revoke through `DELETE /sessions/{id}` has acceptable lag
  (≤ access TTL) for the UX of "sign out this iPad."

If we ever need instant single-token revoke, a Redis set keyed by user_id
with `jti → exp` TTL can be added on top of this scheme without changing
the JWT shape (`jti` is already minted on refresh tokens).

## Related files

- `backend/api/auth/dependencies.py` — `tv` check in `get_current_user`.
- `backend/api/auth/security.py` — JWTHelper (claim flows through `subject` dict).
- `backend/api/auth/device.py` — UA parser + IP hashing.
- `backend/api/routers/auth.py` — `_issue_session`, `logout_all`,
  `logout_others`, `list_sessions`, `revoke_session`.
- `backend/api/repositories/auth_repos.py` — `bump_token_version`,
  `list_active_by_user`, `revoke_by_id`, `touch_last_used`.
- `backend/alembic/versions/022_token_version_and_session_metadata.py`.
