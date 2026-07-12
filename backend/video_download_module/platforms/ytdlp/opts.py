"""yt-dlp options helpers."""

from pathlib import Path


def get_ydl_opts() -> dict:
    """Return extra yt-dlp options from config (cookies, rate-limit controls)."""
    from config.settings import get_settings

    settings = get_settings()
    opts: dict = {}

    # Cookies: raises YouTube rate limit from ~300 to ~2000 videos/hour
    if settings.ytdlp.cookies_file:
        path = Path(settings.ytdlp.cookies_file)
        if path.exists():
            opts["cookiefile"] = str(path.resolve())
    elif settings.ytdlp.cookies_from_browser:
        opts["cookiesfrombrowser"] = (settings.ytdlp.cookies_from_browser.strip().lower(),)

    if settings.ytdlp.sleep_interval:
        opts["sleep_interval"] = settings.ytdlp.sleep_interval
    if settings.ytdlp.max_sleep_interval:
        opts["max_sleep_interval"] = settings.ytdlp.max_sleep_interval

    return opts
