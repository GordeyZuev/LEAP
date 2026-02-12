"""OAuth-related schemas."""

from .responses import (
    OAuthAuthorizeResponse,
    OAuthImplicitFlowResponse,
    VKImplicitFlowCallbackResponse,
)

__all__ = [
    "OAuthAuthorizeResponse",
    "OAuthImplicitFlowResponse",
    "VKImplicitFlowCallbackResponse",
]
