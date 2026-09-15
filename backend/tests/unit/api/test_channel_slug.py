import pytest
from fastapi import HTTPException

from api.helpers.channel_slug import suggest_slug, validate_channel_slug


@pytest.mark.unit
class TestChannelSlug:
    def test_validate_ok(self) -> None:
        assert validate_channel_slug("proga") == "proga"
        assert validate_channel_slug("my_course") == "my_course"
        assert validate_channel_slug("My-Course") == "my-course"

    def test_reserved_and_short(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_channel_slug("share")
        assert exc.value.status_code == 422
        with pytest.raises(HTTPException):
            validate_channel_slug("abc")

    def test_suggest_strips_unicode(self) -> None:
        assert "alg" in suggest_slug("Алгоритмы") or suggest_slug("Алгоритмы") == ""
        assert suggest_slug("Hello World!!").startswith("hello-world")
        assert suggest_slug("CS_101 extra") == "cs_101-extra"
