"""Unit tests for PKCE helpers used by OAuth flows."""

import pytest


@pytest.mark.unit
class TestPKCEHelpers:
    """Tests for PKCE helper functions."""

    def test_generate_pkce_pair(self):
        """Test PKCE code verifier and challenge generation."""
        from api.services.pkce_utils import generate_pkce_pair

        verifier, challenge = generate_pkce_pair()

        assert len(verifier) >= 43  # Min length for PKCE
        assert len(challenge) > 0
        assert verifier != challenge  # Should be different

    def test_code_challenge_is_base64(self):
        """Test that code challenge is base64 URL-safe."""
        from api.services.pkce_utils import generate_code_challenge

        verifier = "test_verifier_123_abc"

        challenge = generate_code_challenge(verifier)

        # Should be base64 URL-safe (no +, /, =)
        assert "+" not in challenge
        assert "/" not in challenge
        assert "=" not in challenge

    def test_pkce_pair_is_unique(self):
        """Test that each PKCE pair is unique."""
        from api.services.pkce_utils import generate_pkce_pair

        verifier1, challenge1 = generate_pkce_pair()
        verifier2, challenge2 = generate_pkce_pair()

        assert verifier1 != verifier2
        assert challenge1 != challenge2
