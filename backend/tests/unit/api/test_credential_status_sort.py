"""Credential list sorting by status (derived from needs_reauth + is_active)."""

from types import SimpleNamespace

import pytest

from api.routers.credentials import CREDENTIAL_SORT_FIELDS, CREDENTIAL_SORT_KEYS, _credential_status_key
from api.schemas.common.pagination import paginate_list


def _cred(name: str, *, needs_reauth: bool = False, is_active: bool = True):
    return SimpleNamespace(account_name=name, platform="zoom", needs_reauth=needs_reauth, is_active=is_active)


@pytest.mark.unit
class TestCredentialStatusSort:
    def test_status_is_an_allowed_sort_field(self):
        assert "status" in CREDENTIAL_SORT_FIELDS
        assert "status" in CREDENTIAL_SORT_KEYS

    def test_ascending_puts_attention_first(self):
        items = [
            _cred("working"),
            _cred("switched-off", is_active=False),
            _cred("dead-key", needs_reauth=True),
        ]

        ordered, _, _ = paginate_list(
            items, 1, 20, "status", "asc", CREDENTIAL_SORT_FIELDS, sort_keys=CREDENTIAL_SORT_KEYS
        )

        assert [c.account_name for c in ordered] == ["dead-key", "switched-off", "working"]

    def test_descending_reverses_the_groups(self):
        items = [_cred("dead-key", needs_reauth=True), _cred("working")]

        ordered, _, _ = paginate_list(
            items, 1, 20, "status", "desc", CREDENTIAL_SORT_FIELDS, sort_keys=CREDENTIAL_SORT_KEYS
        )

        assert [c.account_name for c in ordered] == ["working", "dead-key"]

    def test_same_status_falls_back_to_name(self):
        items = [_cred("zeta"), _cred("alpha")]

        ordered, _, _ = paginate_list(
            items, 1, 20, "status", "asc", CREDENTIAL_SORT_FIELDS, sort_keys=CREDENTIAL_SORT_KEYS
        )

        assert [c.account_name for c in ordered] == ["alpha", "zeta"]

    def test_reauth_outranks_inactive_even_when_both_are_broken(self):
        assert _credential_status_key(_cred("a", needs_reauth=True, is_active=False))[0] == 0

    def test_unknown_sort_field_still_falls_back_to_created_at(self):
        """The derived key must not break the existing allow-list behaviour."""
        items = [
            SimpleNamespace(created_at=2, account_name="b", platform="zoom", needs_reauth=False, is_active=True),
            SimpleNamespace(created_at=1, account_name="a", platform="zoom", needs_reauth=False, is_active=True),
        ]

        ordered, _, _ = paginate_list(
            items, 1, 20, "nonsense", "asc", CREDENTIAL_SORT_FIELDS, sort_keys=CREDENTIAL_SORT_KEYS
        )

        assert [c.created_at for c in ordered] == [1, 2]
