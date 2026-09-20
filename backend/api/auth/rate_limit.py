"""Per-email auth rate limit (login / register / reset)."""

from fastapi import HTTPException, status

from api.dependencies import get_redis
from config.settings import get_settings

settings = get_settings()


async def enforce_auth_email_limit(email: str) -> None:
    """Raise 429 when this email exceeds the auth-per-minute cap.

    Always increments, even for unknown emails, so 429 cannot enumerate accounts.
    """
    if not settings.security.rate_limit_enabled:
        return
    normalized = (email or "").strip().lower()
    if not normalized:
        return
    try:
        redis_client = await get_redis()
        key = f"rl:auth:email:{normalized}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
        if int(count) > settings.security.rate_limit_auth_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Try again in a minute.",
                headers={"Retry-After": "60"},
            )
    except HTTPException:
        raise
    except Exception:
        return
