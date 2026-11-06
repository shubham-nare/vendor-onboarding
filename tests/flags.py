"""Out-of-scope features are off by default (onboarding/features.py). A test module for one of them turns its flag on:

    from tests.flags import flags_on
    _features = flags_on("payables", "intel")

(assign the result to a module-level name; it is an autouse, module-scoped fixture)."""

import pytest


def flags_on(*names: str, scope: str = "module", autouse: bool = True):
    @pytest.fixture(scope=scope, autouse=autouse)
    def _fixture():
        from onboarding.config import get_settings
        mp = pytest.MonkeyPatch()
        for n in names:
            mp.setenv(f"FEATURE_{n.upper()}", "true")
        get_settings.cache_clear()
        yield
        mp.undo()
        get_settings.cache_clear()
    return _fixture
