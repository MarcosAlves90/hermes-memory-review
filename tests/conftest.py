import os
import sys
from contextvars import ContextVar
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(autouse=True)
def hermes_home_context(monkeypatch):
    """Provide Hermes' request-scoped home API to the isolated unit-test runtime."""
    home_override = ContextVar("test_hermes_home_override", default=None)
    module = ModuleType("hermes_constants")

    def set_hermes_home_override(path):
        return home_override.set(None if path is None else str(path))

    def reset_hermes_home_override(token):
        home_override.reset(token)

    def get_hermes_home():
        override = home_override.get()
        if override:
            return Path(override)
        env_home = os.environ.get("HERMES_HOME", "").strip()
        if env_home:
            return Path(env_home)
        return Path.home() / (".hermes" + os.environ.get("HERMES_DATA_DIR_SUFFIX", ""))

    module.set_hermes_home_override = set_hermes_home_override
    module.reset_hermes_home_override = reset_hermes_home_override
    module.get_hermes_home = get_hermes_home
    monkeypatch.setitem(sys.modules, "hermes_constants", module)
    return module
