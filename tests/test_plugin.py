
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT


def load_plugin():
    name = "memory_review_plugin_test"
    sys.modules.pop(name, None)
    sys.modules.pop(name + ".core", None)
    sys.modules.pop(name + ".runtime_bridge", None)
    sys.modules.pop("_hermes_memory_review_runtime_bridge", None)
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

    def __init__(self, settings=None, raise_config=False, llm=None):
        self.settings = settings or {}
        self.raise_config = raise_config
        self.commands = {}
        self.cli_commands = {}
        self.llm = llm
        self.unload_callbacks = []

    def get_config(self, key, default=None):
        if self.raise_config:
            raise RuntimeError("config unavailable")
        return self.settings.get(key, default)

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = {"handler": handler, **kwargs}

    def register_cli_command(self, name, **kwargs):
        self.cli_commands[name] = kwargs

    def on_unload(self, callback):
        self.unload_callbacks.append(callback)


def test_registers_supported_commands(tmp_path):
    plugin = load_plugin()
    ctx = FakeCtx({"home_override": str(tmp_path), "default_page_size": 3, "max_page_size": 7})
    plugin.register(ctx)

    assert set(ctx.commands) == {"memory-review", "memreview", "memory-show", "memory-compact-preview"}
    assert set(ctx.cli_commands) == {"memory-review"}
    assert ctx.commands["memory-review"]["argument_mode"] == "text"
    assert "<id" in ctx.commands["memory-show"]["args_hint"]
    assert "memory|user" in ctx.commands["memory-compact-preview"]["args_hint"]
    bridge = sys.modules["_hermes_memory_review_runtime_bridge"]
    assert bridge.get_plugin_llm() is ctx.llm
    assert len(ctx.unload_callbacks) == 1
    ctx.unload_callbacks[0]()
    try:
        bridge.get_plugin_llm()
    except RuntimeError as exc:
        assert "Agent context is unavailable" in str(exc)
    else:
        raise AssertionError("unload must clear the bound plugin context")


class FakeLlm:
    def __init__(self, entries):
        self.entries = entries
        self.calls = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            parsed={"entries": self.entries},
            text=json.dumps({"entries": self.entries}),
            provider="default-provider",
            model="default-model",
        )


class FakeSequenceLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        entries = self.responses[len(self.calls) - 1]
        return SimpleNamespace(
            parsed={"entries": entries},
            text=json.dumps({"entries": entries}),
            provider="default-provider",
            model="default-model",
        )


class FakePreviewStore:
    def __init__(self, memory=None, user=None):
        self.memory_entries = list(memory or [])
        self.user_entries = list(user or [])


def test_compaction_preview_uses_default_llm_and_returns_reviewable_proposal(monkeypatch, tmp_path):
    plugin = load_plugin()
    llm = FakeLlm(["fact one; fact two detail"])
    ctx = FakeCtx({"home_override": str(tmp_path)}, llm=llm)
    store = FakePreviewStore(
        memory=[
            "The first durable fact is fact one and this sentence contains unnecessary explanation.",
            "The second durable fact is fact two with detail and this sentence repeats unnecessary context.",
        ],
        user=["profile fact"],
    )
    monkeypatch.setattr(plugin, "_memory_store", lambda: store)
    plugin.register(ctx)

    result = json.loads(ctx.commands["memory-compact-preview"]["handler"]("memory"))

    assert result["success"] is True
    assert result["target"] == "memory"
    assert result["proposed_entries"] == ["fact one; fact two detail"]
    assert result["source_fingerprint"] == plugin._source_fingerprint(store.memory_entries)
    assert result["before_tokens"] > result["after_tokens"]
    assert result["token_estimate_method"] == "hermes_memory_budget_2.75_chars_per_token"
    assert result["provider"] == "default-provider"
    assert result["model"] == "default-model"
    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert "provider" not in call
    assert "model" not in call
    assert "untrusted data" in call["system_prompt"].lower()
    assert "fewest coherent" in call["system_prompt"].lower()
    assert "do not" in call["instructions"].lower()


def test_compaction_preview_retries_when_first_proposal_does_not_reduce_footprint(monkeypatch, tmp_path):
    plugin = load_plugin()
    original = ["The user prefers concise answers.", "The user values precise technical detail."]
    llm = FakeSequenceLlm(
        [
            original,
            ["Concise, precise answers."],
        ]
    )
    ctx = FakeCtx({"home_override": str(tmp_path)}, llm=llm)
    store = FakePreviewStore(memory=original)
    monkeypatch.setattr(plugin, "_memory_store", lambda: store)
    plugin.register(ctx)

    result = json.loads(ctx.commands["memory-compact-preview"]["handler"]("memory"))

    assert result["success"] is True
    assert result["attempts"] == 2
    assert len(llm.calls) == 2
    assert "validity requirement" in llm.calls[0]["instructions"].lower()
    assert "hard output budget" in llm.calls[0]["instructions"].lower()
    assert "previous proposal" in llm.calls[1]["instructions"].lower()
    assert "compress this candidate in place" in llm.calls[1]["instructions"].lower()
    assert llm.calls[1]["input"][0]["text"] == plugin._entry_delimiter().join(original)
    assert result["after_tokens"] < result["before_tokens"]


def test_compaction_preview_retries_when_proposal_breaks_advertised_character_budget(monkeypatch, tmp_path):
    plugin = load_plugin()
    original = ["A" * 100, "B" * 100, "C" * 100, "D" * 100]
    llm = FakeSequenceLlm([["X" * 270], ["Y" * 120]])
    ctx = FakeCtx({"home_override": str(tmp_path)}, llm=llm)
    store = FakePreviewStore(memory=original)
    monkeypatch.setattr(plugin, "_memory_store", lambda: store)
    plugin.register(ctx)

    result = json.loads(ctx.commands["memory-compact-preview"]["handler"]("memory"))

    assert result["success"] is True
    assert result["attempts"] == 2
    assert len(llm.calls) == 2
    assert "above its" in llm.calls[1]["instructions"].lower()
    assert llm.calls[1]["input"][0]["text"] == "X" * 270
    assert result["after_chars"] == 120


def test_compaction_preview_targets_core_memory_and_fewer_entries(monkeypatch, tmp_path):
    plugin = load_plugin()
    original = [
        "User prefers concise answers and dislikes filler explanations.",
        "User prefers direct answers with minimal repetition.",
        "User is building Hermes Memory Review.",
        "Hermes Memory Review is a plugin for reviewing stored memory.",
        "The plugin should keep memory actions explicit and reviewable.",
        "The plugin must not mutate stored memory before explicit apply.",
        "User values technical precision in implementation discussions.",
        "User wants implementation details to remain technically precise.",
    ]
    compact = [
        "User prefers concise, direct, technically precise answers without filler or repetition.",
        "Hermes Memory Review: keep memory changes explicit/reviewable; never mutate stored memory before Apply.",
    ]
    llm = FakeLlm(compact)
    ctx = FakeCtx({"home_override": str(tmp_path)}, llm=llm)
    store = FakePreviewStore(memory=original)
    monkeypatch.setattr(plugin, "_memory_store", lambda: store)
    plugin.register(ctx)

    result = json.loads(ctx.commands["memory-compact-preview"]["handler"]("memory"))

    assert result["success"] is True
    assert result["before_entry_count"] == 8
    assert result["after_entry_count"] == 2
    assert result["reduction_percent"] >= 40
    call = llm.calls[0]
    assert call["json_schema"]["properties"]["entries"]["maxItems"] == 2
    instructions = call["instructions"].lower()
    system_prompt = call["system_prompt"].lower()
    assert "source entry boundaries have no semantic value" in system_prompt
    assert "smallest durable representation" in system_prompt
    assert "examples" in system_prompt
    assert "at most 2 entries" in instructions


def test_compaction_preview_retries_when_model_ignores_entry_limit(monkeypatch, tmp_path):
    plugin = load_plugin()
    original = [
        f"Durable source fact {index} with a large amount of redundant explanatory wording that should be compressed."
        for index in range(1, 9)
    ]
    llm = FakeSequenceLlm(
        [
            ["a", "b", "c", "d", "e", "f", "g", "h"],
            ["Core facts 1-4.", "Core facts 5-8."],
        ]
    )
    ctx = FakeCtx({"home_override": str(tmp_path)}, llm=llm)
    store = FakePreviewStore(memory=original)
    monkeypatch.setattr(plugin, "_memory_store", lambda: store)
    plugin.register(ctx)

    result = json.loads(ctx.commands["memory-compact-preview"]["handler"]("memory"))

    assert result["success"] is True
    assert result["attempts"] == 2
    assert result["after_entry_count"] == 2
    assert result["proposed_entries"] == ["Core facts 1-4.", "Core facts 5-8."]
    assert len(llm.calls) == 2
    retry_prompt = llm.calls[1]["instructions"].lower()
    assert "8 entries" in retry_prompt
    assert "maximum of 2" in retry_prompt


def test_compaction_preview_fails_closed_when_model_keeps_ignoring_entry_limit(monkeypatch, tmp_path):
    plugin = load_plugin()
    original = [
        f"Durable source fact {index} with redundant explanatory wording that should be compressed."
        for index in range(1, 9)
    ]
    too_many = ["a", "b", "c", "d", "e", "f", "g", "h"]
    llm = FakeSequenceLlm([too_many, too_many])
    ctx = FakeCtx({"home_override": str(tmp_path)}, llm=llm)
    store = FakePreviewStore(memory=original)
    monkeypatch.setattr(plugin, "_memory_store", lambda: store)
    plugin.register(ctx)

    result = json.loads(ctx.commands["memory-compact-preview"]["handler"]("memory"))

    assert result["success"] is False
    assert result["after_entry_count"] == 8
    assert "maximum of 2 entries" in result["error"]
    assert len(llm.calls) == 2


def test_compaction_preview_rejects_invalid_or_empty_target_without_llm(monkeypatch, tmp_path):
    plugin = load_plugin()
    llm = FakeLlm(["unused"])
    ctx = FakeCtx({"home_override": str(tmp_path)}, llm=llm)
    monkeypatch.setattr(plugin, "_memory_store", lambda: FakePreviewStore())
    plugin.register(ctx)

    invalid = json.loads(ctx.commands["memory-compact-preview"]["handler"]("other"))
    empty = json.loads(ctx.commands["memory-compact-preview"]["handler"]("memory"))

    assert invalid["success"] is False
    assert empty["success"] is False
    assert llm.calls == []


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
