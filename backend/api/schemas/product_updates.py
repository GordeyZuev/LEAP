"""Public and administrative contracts for product updates and feedback."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Interest = Literal["viewers", "course_publishing", "video_processing"]
FeedbackKind = Literal["idea", "problem", "question", "other"]


def _validate_interests(value: list[str]) -> list[str]:
    allowed = {"viewers", "course_publishing", "video_processing"}
    if len(value) != len(set(value)) or not set(value) <= allowed:
        raise ValueError("Select one or more valid interests")
    if not value:
        raise ValueError("Select at least one interest")
    return value


class ProductUpdatePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: str | None
    title: str
    summary: str
    audience_bullets: list[str]
    creator_bullets: list[str]
    release_date: date | None
    published_at: datetime | None


class ProductUpdateAdmin(ProductUpdatePublic):
    model_config = ConfigDict(from_attributes=True)

    audiences: list[str]
    is_published: bool
    newsletter_enabled: bool
    created_at: datetime
    updated_at: datetime
    email_requested_at: datetime | None
    delivery_counts: dict[str, int] = Field(default_factory=dict)


class ProductUpdateWrite(BaseModel):
    version: str | None = Field(default=None, max_length=32)
    title: str = Field(min_length=3, max_length=180)
    summary: str = Field(min_length=3, max_length=300)
    audience_bullets: list[str] = Field(default_factory=list, max_length=20)
    creator_bullets: list[str] = Field(default_factory=list, max_length=20)
    audiences: list[Interest] = Field(default_factory=list)
    newsletter_enabled: bool = False

    @field_validator("version", mode="before")
    @classmethod
    def strip_version(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("audiences")
    @classmethod
    def validate_audiences(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Audience values must be unique")
        return value

    @field_validator("audience_bullets", "creator_bullets", mode="before")
    @classmethod
    def strip_bullets(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        cleaned = []
        for item in value:
            if isinstance(item, str):
                item = item.strip()
                if not item:
                    continue
            cleaned.append(item)
        return cleaned

    @field_validator("audience_bullets", "creator_bullets")
    @classmethod
    def validate_bullets(cls, value: list[str]) -> list[str]:
        if any(len(item) > 300 for item in value):
            raise ValueError("Each release note bullet must be at most 300 characters")
        return value

    @field_validator("title", "summary", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class NewsletterSubscribeRequest(BaseModel):
    email: EmailStr
    interests: list[Interest]

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, value: list[str]) -> list[str]:
        return _validate_interests(value)


class NewsletterTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=128)


class NewsletterPreferencesRequest(NewsletterTokenRequest):
    interests: list[Interest]

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, value: list[str]) -> list[str]:
        return _validate_interests(value)


class NewsletterPreferencesResponse(BaseModel):
    interests: list[Interest]


class NewsletterSubscriptionResponse(BaseModel):
    message: str


class ProductFeedbackRequest(BaseModel):
    interests: list[Interest]
    kind: FeedbackKind
    message: str = Field(min_length=10, max_length=5000)
    reply_email: EmailStr | None = None

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, value: list[str]) -> list[str]:
        return _validate_interests(value)

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class ProductFeedbackAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    interests: list[str]
    kind: str
    message: str
    reply_email: str | None
    created_at: datetime


class ProductNewsStats(BaseModel):
    subscriptions_total: int
    subscriptions_pending: int
    subscriptions_confirmed: int
    subscriptions_unsubscribed: int
    interests: dict[str, int]
    feedback_total: int
    feedback_by_kind: dict[str, int]
    feedback_by_interest: dict[str, int]
    delivery_by_status: dict[str, int]


class ProductNewsAudienceCount(BaseModel):
    count: int
