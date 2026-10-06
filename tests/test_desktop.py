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


def test_desktop_decisions_use_session_independent_backend():
    source = (DESKTOP / "plugin.js").read_text(encoding="utf-8")
    decision_start = source.index("const runDecision")
    decision_end = source.index("ctx.registerMany", decision_start)
    decision_source = source[decision_start:decision_end]
    assert "ctx.rest" in decision_source
    assert "/decision" in decision_source
    assert "slash.exec" not in decision_source
    assert "activeSessionId" not in decision_source
    assert "focusedSessionId" not in decision_source
    assert "['overview', 'Overview']" in source
    assert "useState('overview')" in source
    assert "Approve all" in source and "Reject all" in source
    assert "Confirm ${bulkConfirm} all" in source
    assert "target missing · obsolete proposal" in source
    assert "Delete obsolete" in source
    assert "Cannot approve" in source


def test_pending_detail_text_is_selectable_for_copying():
    source = (DESKTOP / "plugin.js").read_text(encoding="utf-8")

    overview_start = source.index("function OverviewView")
    overview_end = source.index("function PendingWritesPage", overview_start)
    overview_source = source[overview_start:overview_end]
    assert "'data-selectable-text': 'true'" in overview_source

    detail_start = source.index("? view === 'overview'")
    detail_end = source.index(": jsx('div', {", detail_start)
    detail_source = source[detail_start:detail_end]
    assert "'data-selectable-text': 'true'" in detail_source


def test_backend_decisions_do_not_require_chat_session(monkeypatch, tmp_path):
    stage(
        tmp_path,
        "approve123",
        {"action": "replace", "target": "memory", "old_text": "old", "matched_entry": "old", "content": "new"},
    )
    stage(
        tmp_path,
        "reject123",
        {"action": "add", "target": "memory", "content": "discard me"},
        created=2,
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    api = load_api()
    store = FakeMemoryStore(memory=["old"])
    monkeypatch.setattr(api, "_memory_store", lambda: store)
    monkeypatch.setattr(
        api,
        "_apply_pending_memory",
        lambda payload, active_store: active_store.replace(
            payload["target"],
            payload["old_text"],
            payload["content"],
            matched_entry=payload["matched_entry"],
        ),
    )
    client = client_for(api)

    approved = client.post("/records/approve123/decision", json={"action": "approve"})
    rejected = client.post("/records/reject123/decision", json={"action": "reject"})

    assert approved.status_code == 200
    assert approved.json()["success"] is True
    assert "Approved 1 memory write(s)." in approved.json()["output"]
    assert store.memory_entries == ["new"]
    assert not (tmp_path / "pending" / "memory" / "approve123.json").exists()

    assert rejected.status_code == 200
    assert rejected.json()["success"] is True
    assert "Rejected pending memory write 'reject123'." in rejected.json()["output"]
    assert not (tmp_path / "pending" / "memory" / "reject123.json").exists()


def test_backend_bulk_decisions_do_not_require_chat_session(monkeypatch, tmp_path):
    stage(tmp_path, "add-one", {"action": "add", "target": "memory", "content": "one"})
    stage(tmp_path, "add-two", {"action": "add", "target": "memory", "content": "two"}, created=2)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    api = load_api()
    store = FakeMemoryStore()
    monkeypatch.setattr(api, "_memory_store", lambda: store)
    monkeypatch.setattr(
        api,
        "_apply_pending_memory",
        lambda payload, active_store: active_store.add(payload["target"], payload["content"]),
    )
    client = client_for(api)

    approved = client.post("/records/all/decision", json={"action": "approve"})

    assert approved.status_code == 200
    assert "Approved 2 memory write(s)." in approved.json()["output"]
    assert store.memory_entries == ["one", "two"]

    stage(tmp_path, "drop-one", {"action": "add", "target": "memory", "content": "three"}, created=3)
    stage(tmp_path, "drop-two", {"action": "add", "target": "memory", "content": "four"}, created=4)
    rejected = client.post("/records/all/decision", json={"action": "reject"})

    assert rejected.status_code == 200
    assert "Rejected 2 pending memory write(s)." in rejected.json()["output"]
    assert not list((tmp_path / "pending" / "memory").glob("*.json"))


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
    monkeypatch.setattr(api, "_memory_store", lambda: FakeMemoryStore(memory=["old"]))
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
        "target_status": {
            "state": "ready",
            "can_apply": True,
            "missing_count": 0,
            "destructive_count": 1,
        },
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
        add_result=None,
        remove_result=None,
        batch_result=None,
        memory_char_limit=2200,
        user_char_limit=1375,
    ):
        self.memory_entries = list(memory or [])
        self.user_entries = list(user or [])
        self.replace_result = replace_result
        self.add_result = add_result
        self.remove_result = remove_result
        self.batch_result = batch_result
        self.memory_char_limit = memory_char_limit
        self.user_char_limit = user_char_limit
        self.calls = []
        self.add_calls = []
        self.remove_calls = []
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

    def add(self, target, content):
        self.add_calls.append((target, content))
        if self.add_result is not None:
            return self.add_result
        entries = self.memory_entries if target == "memory" else self.user_entries
        if content not in entries:
            entries.append(content)
        return {"success": True, "message": "Entry added."}

    def remove(self, target, old_text, matched_entry=None):
        self.remove_calls.append((target, old_text, matched_entry))
        if self.remove_result is not None:
            return self.remove_result
        entries = self.memory_entries if target == "memory" else self.user_entries
        entries.remove(matched_entry)
        return {"success": True, "message": "Entry removed.", "previous_content": matched_entry}

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


def test_backend_marks_pending_write_obsolete_when_pinned_target_is_missing(monkeypatch, tmp_path):
    stage(
        tmp_path,
        "stale123",
        {"action": "remove", "target": "memory", "old_text": "gone", "matched_entry": "gone"},
        summary="remove stale memory",
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    api = load_api()
    monkeypatch.setattr(api, "_memory_store", lambda: FakeMemoryStore(memory=["still here"]))
    client = client_for(api)

    listing_status = client.get("/records").json()["records"][0]["target_status"]
    detail_status = client.get("/records/stale123").json()["record"]["target_status"]

    assert listing_status == detail_status
    assert detail_status["state"] == "missing"
    assert detail_status["can_apply"] is False
    assert detail_status["missing_count"] == 1
    assert "reject it to delete the proposal" in detail_status["message"].lower()


def test_backend_marks_batch_obsolete_when_any_pinned_target_is_missing(monkeypatch, tmp_path):
    stage(
        tmp_path,
        "batch-stale",
        {
            "action": "batch",
            "target": "user",
            "operations": [
                {"action": "replace", "old_text": "present", "matched_entry": "present", "content": "new"},
                {"action": "remove", "old_text": "gone", "matched_entry": "gone"},
                {"action": "add", "content": "added"},
            ],
        },
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    api = load_api()
    monkeypatch.setattr(api, "_memory_store", lambda: FakeMemoryStore(user=["present"]))

    status = client_for(api).get("/records/batch-stale").json()["record"]["target_status"]

    assert status["state"] == "missing"
    assert status["can_apply"] is False
    assert status["missing_count"] == 1
    assert status["destructive_count"] == 2


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


def test_backend_adds_stored_memory_entry_through_memory_store(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(memory=["existing"], user=["profile"])
    monkeypatch.setattr(api, "_memory_store", lambda: store)

    response = client_for(api).post("/memory/memory/entries", json={"content": "new entry"})

    assert response.status_code == 200
    assert store.add_calls == [("memory", "new entry")]
    assert response.json()["target"]["entries"] == [
        {"index": 0, "content": "existing"},
        {"index": 1, "content": "new entry"},
    ]


def test_backend_deletes_exact_stored_memory_entry_through_memory_store(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(memory=["keep", "remove me"], user=["profile"])
    monkeypatch.setattr(api, "_memory_store", lambda: store)

    response = client_for(api).request(
        "DELETE",
        "/memory/memory/entries",
        json={"old_text": "remove me"},
    )

    assert response.status_code == 200
    assert store.remove_calls == [("memory", "remove me", "remove me")]
    assert response.json()["target"]["entries"] == [{"index": 0, "content": "keep"}]


def test_backend_surfaces_add_remove_failures_without_mutation_success(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(
        memory=["existing"],
        add_result={"success": False, "error": "Memory limit exceeded."},
        remove_result={"success": False, "error": "Entry changed since it was reviewed."},
    )
    monkeypatch.setattr(api, "_memory_store", lambda: store)

    add_response = client_for(api).post("/memory/memory/entries", json={"content": "too large"})
    remove_response = client_for(api).request(
        "DELETE",
        "/memory/memory/entries",
        json={"old_text": "existing"},
    )

    assert add_response.status_code == 409
    assert remove_response.status_code == 409
    assert add_response.json()["detail"]["success"] is False
    assert remove_response.json()["detail"]["success"] is False


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
    assert "Add entry" in source
    assert "Delete entry" in source
    assert "Confirm delete" in source
    assert "Search stored memory" in source
    assert "estimated_tokens" in source
    assert "estimated_token_limit" in source
    assert "usage_percent" in source
    assert "used_chars" in source
    assert "char_limit" in source
    assert "used" in source
    assert "tokens estimated" in source
    assert "Compact with AI" in source
    assert "AI compaction in progress" in source
    assert "compactionElapsed" in source
    assert "setInterval" in source
    assert "automatically retry" in source
    stored_start = source.index("function StoredMemoryPage")
    stored_end = source.index("function MemoryReviewPage", stored_start)
    stored_source = source[stored_start:stored_end]
    assert "max-h-[40vh]" in stored_source
    assert "shrink-0" in stored_source
    assert "overflow-hidden" in stored_source
    assert "before_entry_count" in stored_source
    assert "reduction_percent" in stored_source
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
    assert "/entries" in source


def test_backend_generates_compaction_preview_without_a_chat_session(monkeypatch):
    api = load_api()
    store = FakeMemoryStore(
        memory=[
            "The first durable fact is first fact with unnecessary explanatory wording.",
            "The second durable fact is second fact with detail and repeated explanatory wording.",
        ],
        user=["profile"],
    )
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
    assert "untrusted data" in call["system_prompt"].lower()
    assert "fewest coherent" in call["system_prompt"].lower()
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
