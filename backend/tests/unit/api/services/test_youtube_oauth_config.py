"""YouTube OAuth configuration requirements for API access."""

from api.routers.oauth import _build_oauth_credentials
from api.services.oauth_platforms import create_youtube_config


def test_youtube_oauth_config_can_use_server_environment_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("YOUTUBE_OAUTH_CONFIG", str(tmp_path / "missing-oauth-client.json"))
    monkeypatch.setenv("OAUTH_YOUTUBE_CLIENT_ID", "youtube-client-id")
    monkeypatch.setenv("OAUTH_YOUTUBE_CLIENT_SECRET", "youtube-client-secret")
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "https://app.example.test")
    create_youtube_config.cache_clear()

    try:
        config = create_youtube_config()
    finally:
        create_youtube_config.cache_clear()

    assert config.client_id == "youtube-client-id"
    assert config.client_secret == "youtube-client-secret"
    assert config.redirect_uri == "https://app.example.test/api/v1/oauth/youtube/callback"
    assert "https://www.googleapis.com/auth/youtube.upload" in config.scopes
    assert "https://www.googleapis.com/auth/youtube.force-ssl" in config.scopes


def test_youtube_credentials_store_scopes_granted_by_google(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("YOUTUBE_OAUTH_CONFIG", str(tmp_path / "missing-oauth-client.json"))
    create_youtube_config.cache_clear()
    config = create_youtube_config()
    create_youtube_config.cache_clear()

    credentials = _build_oauth_credentials(
        "youtube",
        {"access_token": "access-token", "scope": "https://www.googleapis.com/auth/youtube.upload"},
        config,
    )

    assert credentials["token"]["scopes"] == ["https://www.googleapis.com/auth/youtube.upload"]
