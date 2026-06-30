"""Guard test: every usage-counter name must map to a real repository method.

Regression guard for the bug where the method name was built via
f"increment_{counter}s" — which produced "increment_processings" for the
"processing" counter, a method that does not exist.
"""

import pytest


@pytest.mark.unit
def test_counter_methods_exist_on_repository():
    from api.repositories.subscription_repos import QuotaUsageRepository
    from api.tasks.processing import _COUNTER_METHODS

    for counter, method_name in _COUNTER_METHODS.items():
        assert hasattr(QuotaUsageRepository, method_name), f"counter '{counter}' maps to missing method '{method_name}'"


@pytest.mark.unit
def test_all_call_sites_use_known_counters():
    """The three call sites pass 'transcription', 'processing', 'upload'."""
    from api.tasks.processing import _COUNTER_METHODS

    assert set(_COUNTER_METHODS) == {"transcription", "processing", "upload"}
