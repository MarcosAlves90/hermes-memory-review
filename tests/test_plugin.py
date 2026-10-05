
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT


def load_plugin():
    name = "memory_review_plugin_test"
    sys.modules.pop(name, None)
    sys.modules.pop(name + ".core", None)
    spec = importlib.util.spec_from_file_location(
        name,
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeCtx:
    profile_name = "default"

    def __init__(self, settings=None, raise_config=False):
        self.settings = settings or {}
        self.raise_config = raise_config
        self.commands = {}
        self.cli_commands = {}

    def get_config(self, key, default=None):
        if self.raise_config:
            raise RuntimeError("config unavailable")
        return self.settings.get(key, default)

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = {"handler": handler, **kwargs}

    def register_cli_command(self, name, **kwargs):
        self.cli_commands[name] = kwargs


def test_registers_supported_commands(tmp_path):
    plugin = load_plugin()
    ctx = FakeCtx({"home_override": str(tmp_path), "default_page_size": 3, "max_page_size": 7})
    plugin.register(ctx)

    assert set(ctx.commands) == {"memory-review", "memreview", "memory-show"}
    assert set(ctx.cli_commands) == {"memory-review"}
    assert ctx.commands["memory-review"]["argument_mode"] == "text"
    assert "<id" in ctx.commands["memory-show"]["args_hint"]


def test_slash_and_shortcut_handlers(tmp_path):
    plugin = load_plugin()
    ctx = FakeCtx({"home_override": str(tmp_path)})
    plugin.register(ctx)

    out = ctx.commands["memory-review"]["handler"]("list")
    assert "No pending memory writes" in out

    assert "Usage: /memory-show" in ctx.commands["memory-show"]["handler"]("")
    assert "Invalid arguments" in ctx.commands["memory-review"]["handler"]('"unterminated')
    assert "Invalid arguments" in ctx.commands["memory-show"]["handler"]('"unterminated')


def test_review_falls_back_when_config_unavailable(monkeypatch, tmp_path):
    plugin = load_plugin()
    ctx = FakeCtx(raise_config=True)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    review = plugin._review(ctx)
    assert review.home == tmp_path.resolve()
    assert review.default_page_size == 20
    assert review.max_page_size == 100


def test_setup_cli_and_cli_handler(tmp_path, capsys):
    plugin = load_plugin()
    ctx = FakeCtx({"home_override": str(tmp_path)})
    plugin.register(ctx)

    import argparse
    parser = argparse.ArgumentParser()
    setup = ctx.cli_commands["memory-review"]["setup_fn"]
    setup(parser)
    ns = parser.parse_args(["stats"])
    handler = ctx.cli_commands["memory-review"]["handler_fn"]
    handler(ns)
    out = capsys.readouterr().out
    assert "Valid records: 0" in out
