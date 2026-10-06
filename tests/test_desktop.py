import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
DESKTOP = ROOT / "desktop"


def stage(home: Path, pid: str, payload: dict, summary="summary", origin="foreground", created=1):
    pending = home / "pending" / "memory"
    pending.mkdir(parents=True, exist_ok=True)
    record = {
        "id": pid,
        "subsystem": "memory",
        "action": payload.get("action", ""),
        "summary": summary,
        "origin": origin,
        "created_at": created,
        "payload": payload,
    }
    (pending / f"{pid}.json").write_text(json.dumps(record), encoding="utf-8")


def load_api():
    manifest_path = DASHBOARD / "manifest.json"
    assert manifest_path.is_file(), "desktop plugin manifest is required"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest == {"name": "memory-review", "api": "plugin_api.py"}

    api_path = DASHBOARD / manifest["api"]
    assert api_path.is_file()
    name = "memory_review_dashboard_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, api_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def client_for(api):
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def test_unified_desktop_package_uses_documented_surfaces():
    load_api()
    source = (DESKTOP / "plugin.js").read_text(encoding="utf-8")
    assert "@hermes/plugin-sdk" in source
    assert "ROUTES_AREA" in source
    assert "SIDEBAR_NAV_AREA" in source
    assert "data: { path: '/memory-review'" in source
    assert "ctx.rest('/records')" in source
    assert "ctx.rest('/memory')" in source
    assert "method: 'PUT'" in source
    assert "refetchInterval" in source
    assert "querySelector" not in source
    assert "document." not in source


def test_desktop_decisions_use_native_hermes_memory_commands():
    source = (DESKTOP / "plugin.js").read_text(encoding="utf-8")
    assert "host.request('slash.exec'" in source, "desktop decision actions must use Hermes slash.exec"
    assert "command: `/memory ${action} ${target}`" in source
    assert "['overview', 'Overview']" in source
    assert "useState('overview')" in source
    assert "Approve all" in source and "Reject all" in source
    assert "Confirm ${bulkConfirm} all" in source


def test_backend_lists_and_renders_pending_records(monkeypatch, tmp_path):
    stage(
        tmp_path,
        "abc123",
        {"action": "replace", "target": "memory", "old_text": "old", "matched_entry": "old", "content": "new"},
        summary="replace preference",
        origin="background_review",
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    api = load_api()
    client = client_for(api)

    listing = client.get("/records")
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["count"] == 1
    assert payload["issues"] == []
    assert payload["records"][0] == {
        "id": "abc123",
        "action": "replace",
        "target": "memory",
        "origin": "background_review",
        "summary": "replace preference",
        "created_at": 1.0,
    }

    detail = client.get("/records/abc123")
    assert detail.status_code == 200
    data = detail.json()
    assert data["id"] == "abc123"
    assert data["payload"] == {
        "action": "replace",
        "target": "memory",
        "old_text": "old",
        "matched_entry": "old",
        "content": "new",
    }
    assert "Pending memory write abc123" in data["proposal"]
    assert "old" in data["diff"] and "new" in data["diff"]
    assert '"id": "abc123"' in data["raw"]
    assert "OK abc123" in data["verify"]


class FakeMemoryStore:
    def __init__(
        self,
        memory=None,
        user=None,
        replace_result=None,
        batch_result=None,
        memory_char_limit=2200,
        user_char_limit=1375,
    ):
        self.memory_entries = list(memory or [])
        self.user_entries = list(user or [])
        self.replace_result = replace_result
        self.batch_result = batch_result
        self.memory_char_limit = memory_char_limit
        self.user_char_limit = user_char_limit
        self.calls = []
        self.batch_calls = []

    def _char_count(self, target):
        entries = self.memory_entries if target == "memory" else self.user_entries
        return len("\n§\n".join(entries))

    def _char_limit(self, target):
        return self.memory_char_limit if target == "memory" else self.user_char_limit

    def replace(self, target, old_text, content, matched_entry=None):
        self.calls.append((target, old_text, content, matched_entry))
        if self.replace_result is not None:
            return self.replace_result
        entries = self.memory_entries if target == "memory" else self.user_entries
        index = entries.index(matched_entry)
        entries[index] = content
        return {"success": True, "message": "Entry replaced.", "replaced_entry": old_text}

    def apply_batch(self, target, operations):
        self.batch_calls.append((target, operations))
        if self.batch_result is not None:
            return self.batch_result
        entries = self.memory_entries if target == "memory" else self.user_entries
        working = list(entries)
        for operation in operations:
            if operation["action"] == "remove":
                working.remove(operation["matched_entry"])
            elif operation["action"] == "add":
                if operation["content"] not in working:
                    working.append(operation["content"])
        if target == "memory":
            self.memory_entries = working
        else:
            self.user_entries = working
        return {"success": True, "message": "Applied compaction."}


class FakeCompactionLlm:
    def __init__(self, entries=None):
        self.entries = list(entries or ["first fact; second fact"])
        self.calls = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            parsed={"entries": self.entries},
            text=json.dumps({"entries": self.entries}),
            provider="default-provider",
            model="default-model",
        )


def test_backend_lists_stored_memory_for_both_targets(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(memory=["agent note", "second note"], user=["user profile"])
    monkeypatch.setattr(api, "_memory_store", lambda: store)

    response = client_for(api).get("/memory")
    assert response.status_code == 200
    body = response.json()
    assert "estimated_tokens" in body["targets"]["memory"], "token estimate metadata is required"
    assert body == {
        "targets": {
            "memory": {
                "target": "memory",
                "count": 2,
                "used_chars": 24,
                "char_limit": 2200,
                "usage_percent": 1.1,
                "estimated_tokens": 9,
                "estimated_token_limit": 800,
                "token_estimate_method": "hermes_memory_budget_2.75_chars_per_token",
                "entries": [
                    {"index": 0, "content": "agent note"},
                    {"index": 1, "content": "second note"},
                ],
            },
            "user": {
                "target": "user",
                "count": 1,
                "used_chars": 12,
                "char_limit": 1375,
                "usage_percent": 0.9,
                "estimated_tokens": 4,
                "estimated_token_limit": 500,
                "token_estimate_method": "hermes_memory_budget_2.75_chars_per_token",
                "entries": [{"index": 0, "content": "user profile"}],
            },
        }
    }


def test_backend_replaces_exact_stored_memory_entry(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(memory=["old entry"], user=["profile"])
    monkeypatch.setattr(api, "_memory_store", lambda: store)

    response = client_for(api).put(
        "/memory/memory",
        json={"old_text": "old entry", "content": "new entry"},
    )
    assert response.status_code == 200
    assert store.calls == [("memory", "old entry", "new entry", "old entry")]
    body = response.json()
    assert body["success"] is True
    assert body["target"]["entries"] == [{"index": 0, "content": "new entry"}]


def test_backend_rejects_invalid_stored_memory_target(monkeypatch):
    api = load_api()
    monkeypatch.setattr(api, "_memory_store", lambda: FakeMemoryStore())
    response = client_for(api).put(
        "/memory/other",
        json={"old_text": "old", "content": "new"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "target must be 'memory' or 'user'."


def test_backend_surfaces_memory_store_failure_without_success(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(
        memory=["old entry"],
        replace_result={"success": False, "error": "Entry changed since it was reviewed."},
    )
    monkeypatch.setattr(api, "_memory_store", lambda: store)
    response = client_for(api).put(
        "/memory/memory",
        json={"old_text": "old entry", "content": "new entry"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["success"] is False
    assert "changed" in response.json()["detail"]["error"]


def test_desktop_stored_memory_mode_exposes_both_targets_and_editing():
    source = (DESKTOP / "plugin.js").read_text(encoding="utf-8")
    assert "Pending writes" in source
    assert "Stored memory" in source
    assert "['memory', 'Memory']" in source
    assert "['user', 'User']" in source
    assert "Save changes" in source
    assert "Search stored memory" in source
    assert "estimated_tokens" in source
    assert "estimated_token_limit" in source
    assert "usage_percent" in source
    assert "used_chars" in source
    assert "char_limit" in source
    assert "used" in source
    assert "tokens estimated" in source
    assert "Compact with AI" in source
    assert "Apply compaction" in source
    assert "Cancel preview" in source
    preview_start = source.index("const requestCompaction")
    preview_end = source.index("const applyCompaction", preview_start)
    preview_source = source[preview_start:preview_end]
    assert "/compact/preview" in preview_source
    assert "ctx.rest" in preview_source
    assert "slash.exec" not in preview_source
    assert "activeSessionId" not in preview_source
    assert "focusedSessionId" not in preview_source


def test_backend_generates_compaction_preview_without_a_chat_session(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(memory=["first fact", "second fact with detail"], user=["profile"])
    llm = FakeCompactionLlm(["first fact; second fact with detail"])
    monkeypatch.setattr(api, "_memory_store", lambda: store)
    monkeypatch.setattr(api, "_plugin_llm", lambda: llm, raising=False)

    response = client_for(api).post("/memory/memory/compact/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["target"] == "memory"
    assert body["provider"] == "default-provider"
    assert body["model"] == "default-model"
    assert body["proposed_entries"] == ["first fact; second fact with detail"]
    assert body["source_fingerprint"] == api._source_fingerprint(store.memory_entries)
    assert body["before_tokens"] > body["after_tokens"]
    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert "provider" not in call
    assert "model" not in call
    assert "untrusted data" in call["instructions"].lower()
    assert "preserve" in call["instructions"].lower()


def test_backend_applies_compaction_as_one_stale_safe_batch(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(memory=["first fact", "second fact"], user=["profile"])
    monkeypatch.setattr(api, "_memory_store", lambda: store)
    fingerprint = api._source_fingerprint(store.memory_entries)

    response = client_for(api).post(
        "/memory/memory/compact",
        json={"source_fingerprint": fingerprint, "entries": ["first and second fact"]},
    )

    assert response.status_code == 200
    assert len(store.batch_calls) == 1
    target, operations = store.batch_calls[0]
    assert target == "memory"
    assert operations == [
        {"action": "remove", "old_text": "first fact", "matched_entry": "first fact"},
        {"action": "remove", "old_text": "second fact", "matched_entry": "second fact"},
        {"action": "add", "content": "first and second fact"},
    ]
    assert response.json()["target"]["entries"] == [{"index": 0, "content": "first and second fact"}]


def test_backend_rejects_stale_compaction_without_mutation(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(memory=["newer memory"], user=[])
    monkeypatch.setattr(api, "_memory_store", lambda: store)

    response = client_for(api).post(
        "/memory/memory/compact",
        json={"source_fingerprint": api._source_fingerprint(["older memory"]), "entries": ["compact"]},
    )

    assert response.status_code == 409
    assert store.batch_calls == []
    assert store.memory_entries == ["newer memory"]


def test_backend_surfaces_compaction_batch_failure_without_partial_write(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(
        memory=["fact"],
        batch_result={"success": False, "error": "Compaction rejected."},
    )
    monkeypatch.setattr(api, "_memory_store", lambda: store)

    response = client_for(api).post(
        "/memory/memory/compact",
        json={"source_fingerprint": api._source_fingerprint(["fact"]), "entries": ["short fact"]},
    )

    assert response.status_code == 409
    assert len(store.batch_calls) == 1
    assert store.memory_entries == ["fact"]


def test_backend_returns_not_found_for_unknown_record(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    api = load_api()
    response = client_for(api).get("/records/missing")
    assert response.status_code == 404
    assert response.json()["detail"] == "No pending memory write with id/prefix 'missing'."
