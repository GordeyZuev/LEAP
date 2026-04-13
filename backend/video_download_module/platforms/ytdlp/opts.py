"""yt-dlp options helpers — cookies, etc."""

from pathlib import Path


def get_cookie_opts() -> dict:
    """Return cookie-related yt-dlp options from config.

    Use when YouTube blocks requests with "Sign in to confirm you're not a bot".
    Supports:
    - YTDLP_COOKIES_FILE: path to Netscape-format cookies file (recommended for production)
    - YTDLP_COOKIES_FROM_BROWSER: browser name (chrome, firefox, etc.) — requires browser on server
    """
    from config.settings import get_settings

    settings = get_settings()
    opts: dict = {}

    if settings.ytdlp.cookies_file:
        path = Path(settings.ytdlp.cookies_file)
        if path.exists():
            opts["cookiefile"] = str(path.resolve())
        # else: file missing, skip (don't fail at config load)
    elif settings.ytdlp.cookies_from_browser:
        opts["cookiesfrombrowser"] = (settings.ytdlp.cookies_from_browser.strip().lower(),)

    return opts
