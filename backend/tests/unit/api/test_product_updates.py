"""Validation tests for public product-news contracts."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import database.automation_models  # noqa: F401 - register all Base relationships before ORM instance creation
from api.routers import product_updates
from api.schemas.product_updates import (
    NewsletterSubscribeRequest,
    ProductUpdateWrite,
)
from database.product_update_models import NewsletterSubscriptionModel


def test_product_update_write_normalizes_text_and_bullets() -> None:
    update = ProductUpdateWrite(
        title="  A release  ",
        summary="  A short note.  ",
        audience_bullets=["  Audience detail  ", "", "   "],
        creator_bullets=[" Creator detail "],
    )

    assert update.title == "A release"
    assert update.summary == "A short note."
    assert update.audience_bullets == ["Audience detail"]
    assert update.creator_bullets == ["Creator detail"]


def test_product_update_write_rejects_empty_note_after_trimming() -> None:
    with pytest.raises(ValidationError):
        ProductUpdateWrite(title="A release", summary="   ")


def test_product_update_write_rejects_bullets_over_300_characters() -> None:
    with pytest.raises(ValidationError, match="at most 300 characters"):
        ProductUpdateWrite(title="A release", summary="A note", creator_bullets=["x" * 301])


def test_subscription_requires_unique_valid_interests() -> None:
    with pytest.raises(ValidationError):
        NewsletterSubscribeRequest(email="person@example.com", interests=[])
    with pytest.raises(ValidationError):
        NewsletterSubscribeRequest(email="person@example.com", interests=["viewers", "viewers"])


@pytest.mark.asyncio
async def test_failed_confirmation_email_allows_immediate_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    subscription = NewsletterSubscriptionModel(
        id="00000000000000000000000001",
        email="person@example.com",
        interests=["viewers"],
        status="pending",
        confirmation_token_hash="old-hash",
        consented_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=subscription),
        commit=AsyncMock(),
        add=Mock(),
    )

    class EmailService:
        product_news_ready = True

        def __init__(self) -> None:
            self.fail = True

        async def send_product_news_confirmation(self, _email: str, _url: str) -> None:
            if self.fail:
                raise RuntimeError("SMTP unavailable")

    email_service = EmailService()
    monkeypatch.setattr(product_updates, "get_email_service", lambda: email_service)
    monkeypatch.setattr(product_updates, "frontend_url", lambda path: f"https://leap.example{path}")
    request = NewsletterSubscribeRequest(email="person@example.com", interests=["viewers"])

    with pytest.raises(HTTPException) as exc_info:
        await product_updates.subscribe_to_product_news(request, session)

    assert exc_info.value.status_code == 503
    assert subscription.updated_at < datetime.now(UTC) - timedelta(seconds=60)
    assert session.commit.await_count == 2

    email_service.fail = False
    response = await product_updates.subscribe_to_product_news(request, session)

    assert response["message"].startswith("If the address can be subscribed")
    assert session.commit.await_count == 3


@pytest.mark.asyncio
async def test_admin_news_stats_use_the_shared_aggregate_view() -> None:
    rows = [
        ("subscription_status", "confirmed", 4),
        ("subscription_status", "pending", 2),
        ("subscription_interest", "viewers", 3),
        ("delivery_status", "sent", 5),
        ("delivery_status", "failed", 1),
        ("feedback_kind", "idea", 2),
        ("feedback_interest", "video_processing", 2),
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=Mock(return_value=rows))))

    stats = await product_updates.admin_product_news_stats(session, _admin=Mock())

    assert stats.subscriptions_total == 6
    assert stats.subscriptions_confirmed == 4
    assert stats.subscriptions_pending == 2
    assert stats.interests == {"viewers": 3, "course_publishing": 0, "video_processing": 0}
    assert stats.feedback_total == 2
    assert stats.feedback_by_kind == {"idea": 2}
    assert stats.feedback_by_interest == {"viewers": 0, "course_publishing": 0, "video_processing": 2}
    assert stats.delivery_by_status == {"sent": 5, "failed": 1}
