"""Credential decrypt requires owning user_id."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.credential_service import CredentialService


@pytest.fixture
def service():
    with patch("api.services.credential_service.get_encryption"):
        yield CredentialService(MagicMock())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_credentials_by_id_scopes_to_user(service):
    cred = MagicMock()
    cred.is_active = True
    cred.encrypted_data = b"enc"
    cred.id = 7
    cred.user_id = "owner"
    cred.platform = "youtube"
    service.repo.get_by_id = AsyncMock(return_value=cred)
    service._decrypt_and_reencrypt = AsyncMock(return_value={"token": "x"})

    result = await service.get_credentials_by_id(7, "owner")

    assert result == {"token": "x"}
    service.repo.get_by_id.assert_awaited_once_with(7, "owner")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_credentials_by_id_missing_is_value_error(service):
    service.repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await service.get_credentials_by_id(7, "owner")
