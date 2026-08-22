"""Yandex Disk path normalization helpers."""


def normalize_disk_path(path: str) -> str:
    """Normalize a Disk folder path for API calls and storage.

    Examples:
        disk:/Video/Lectures -> /Video/Lectures
        Video/Lectures -> /Video/Lectures
        /Video/ -> /Video
    """
    raw = path.strip()
    if not raw:
        return "/"

    if raw.lower().startswith("disk:"):
        raw = raw[5:].lstrip("/")

    if not raw.startswith("/"):
        raw = f"/{raw}"

    if raw != "/" and raw.endswith("/"):
        raw = raw.rstrip("/")

    return raw or "/"
