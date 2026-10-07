import json
import os
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR))

from core import MagiReview, resolve_hermes_home


def stage(home: Path, pid: str, payload: dict, summary="summary", origin="foreground", created=1):
    d = home / "pending" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    record = {
        "id": pid,
        "subsystem": "memory",
        "action": payload.get("action", ""),
        "summary": summary,
        "origin": origin,
        "created_at": created,
        "payload": payload,
    }
    (d / f"{pid}.json").write_text(json.dumps(record), encoding="utf-8")


def test_show_preserves_long_content(tmp_path):
    content = "full " + ("x" * 500)
    stage(tmp_path, "abcd1234", {"action": "add", "target": "memory", "content": content})
    out = MagiReview(tmp_path).show("abcd")
    assert content in out
    assert "Pending memory write abcd1234" in out


def test_unique_prefix_and_ambiguous_prefix(tmp_path):
    stage(tmp_path, "abcd1111", {"action": "add", "target": "memory", "content": "one"})
    stage(tmp_path, "abce2222", {"action": "add", "target": "memory", "content": "two"}, created=2)
    assert "one" in MagiReview(tmp_path).show("abcd")
    assert "Ambiguous" in MagiReview(tmp_path).show("abc")


def test_diff_replace_uses_pinned_entry(tmp_path):
    stage(tmp_path, "r1", {
        "action": "replace",
        "target": "memory",
        "old_text": "old",
        "matched_entry": "old whole entry\n",
        "content": "new whole entry\n",
    })
    out = MagiReview(tmp_path).diff("r1")
    assert "old whole entry" in out
    assert "new whole entry" in out
    assert "--- operation:before" in out
    assert "+++ operation:after" in out


def test_verify_warns_unpinned_remove(tmp_path):
    stage(tmp_path, "rm1", {
        "action": "remove",
        "target": "memory",
        "old_text": "legacy target",
    })
    out = MagiReview(tmp_path).verify("rm1")
    assert "WARN" in out
    assert "matched_entry" in out


def test_control_sequences_are_escaped(tmp_path):
    stage(tmp_path, "esc1", {
        "action": "add",
        "target": "memory",
        "content": "hello\x1b[31mred",
    })
    out = MagiReview(tmp_path).show("esc1")
    assert "\x1b" not in out
    assert "\\u001b" in out


def test_find_searches_payload(tmp_path):
    stage(tmp_path, "f1", {"action": "add", "target": "user", "content": "favorite editor is neovim"})
    assert "f1" in MagiReview(tmp_path).find("neovim")


def test_oldest_newest(tmp_path):
    stage(tmp_path, "old", {"action": "add", "target": "memory", "content": "first"}, created=1)
    stage(tmp_path, "new", {"action": "add", "target": "memory", "content": "second"}, created=2)
    r = MagiReview(tmp_path)
    assert "first" in r.show("oldest")
    assert "second" in r.show("newest")


def test_path_traversal_selector_cannot_escape(tmp_path):
    stage(tmp_path, "safe", {"action": "add", "target": "memory", "content": "ok"})
    out = MagiReview(tmp_path).show("../../etc/passwd")
    assert "No pending memory write" in out


def test_list_paginates(tmp_path):
    for i in range(5):
        stage(tmp_path, f"id{i}", {"action": "add", "target": "memory", "content": str(i)}, created=i)
    out = MagiReview(tmp_path, default_page_size=2).list_records(2, 2)
    assert "page 2/3" in out
    assert "id2" in out and "id3" in out
    assert "id0" not in out


def test_empty_store_surfaces_useful_messages(tmp_path):
    r = MagiReview(tmp_path)
    assert "No pending memory writes" in r.list_records()
    assert "No pending memory writes" in r.show("newest")
    assert "No pending memory writes" in r.verify("newest")
    assert "No pending memory writes to verify" in r.verify("all")


def test_malformed_files_are_reported(tmp_path):
    d = tmp_path / "pending" / "memory"
    d.mkdir(parents=True)
    (d / "array.json").write_text("[]", encoding="utf-8")
    (d / "broken.json").write_text("{", encoding="utf-8")
    r = MagiReview(tmp_path)
    assert "Skipped malformed files: 2" in r.list_records()
    out = r.verify("all")
    assert "array.json" in out
    assert "broken.json" in out
    assert "2 error(s)" in out


def test_batch_validation_and_diff(tmp_path):
    stage(tmp_path, "batch1", {
        "action": "batch",
        "target": "memory",
        "operations": [
            {"action": "add", "content": "new"},
            {"action": "replace", "old_text": "old", "matched_entry": "old entry\n", "content": "new entry\n"},
            {"action": "remove", "old_text": "delete", "matched_entry": "delete entry\n"},
        ],
    })
    r = MagiReview(tmp_path)
    out = r.verify("batch1")
    assert "OK batch1" in out
    diff = r.diff("batch1")
    assert "operation 1 [add]" in diff
    assert "operation 2 [replace]" in diff
    assert "operation 3 [remove]" in diff


def test_invalid_payloads_report_errors_and_warnings(tmp_path):
    d = tmp_path / "pending" / "memory"
    d.mkdir(parents=True)

    records = {
        "badpayload": {"id": "badpayload", "subsystem": "memory", "payload": "nope"},
        "badtarget": {"id": "other-id", "subsystem": "other", "payload": {"action": "add", "target": "x", "content": ""}},
        "badbatch": {"id": "badbatch", "subsystem": "memory", "payload": {"action": "batch", "target": "memory", "operations": []}},
        "badop": {"id": "badop", "subsystem": "memory", "payload": {"action": "batch", "target": "memory", "operations": ["not-object", {"action": "wat"}]}},
        "badreplace": {"id": "badreplace", "subsystem": "memory", "payload": {"action": "replace", "target": "memory", "old_text": "", "content": 3}},
        "badremove": {"id": "badremove", "subsystem": "memory", "payload": {"action": "remove", "target": "memory", "old_text": ""}},
    }
    for name, data in records.items():
        (d / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

    r = MagiReview(tmp_path)
    all_out = r.verify("all")
    assert "payload is missing or is not an object" in all_out
    assert "expected 'memory'" in all_out
    assert "expected 'memory' or 'user'" in all_out
    assert "batch requires a non-empty operations list" in all_out
    assert "operation must be an object" in all_out
    assert "unsupported action" in all_out
    assert "replace requires non-empty old_text" in all_out
    assert "replace requires string content" in all_out
    assert "replace has no matched_entry pin" in all_out
    assert "remove requires non-empty old_text" in all_out


def test_show_surfaces_validation_diagnostics(tmp_path):
    stage(tmp_path, "badadd", {"action": "add", "target": "wrong", "content": ""})
    out = MagiReview(tmp_path).show("badadd")
    assert "Validation:" in out
    assert "ERROR:" in out


def test_raw_path_stats_and_find_edge_cases(tmp_path):
    stage(tmp_path, "s1", {"action": "add", "target": "memory", "content": "alpha"}, summary="alpha", origin="background_review")
    stage(tmp_path, "s2", {"action": "remove", "target": "user", "old_text": "beta", "matched_entry": "beta"}, summary="beta", created=2)
    r = MagiReview(tmp_path, max_page_size=1)

    assert '"id": "s1"' in r.raw("s1")
    assert r.path("s1").endswith("s1.json")
    assert "Actions:" in r.stats()
    assert "Targets:" in r.stats()
    assert "Origins:" in r.stats()
    assert "background_review=1" in r.stats()
    assert r.find("") == "Usage: find <text>"
    assert "... 1 more" in r.find("a")


def test_list_handles_auto_empty_page_and_limits(tmp_path):
    stage(tmp_path, "l1", {"action": "add", "target": "memory", "content": "x"}, origin="background_review")
    r = MagiReview(tmp_path, default_page_size=1, max_page_size=2)
    out = r.list_records(1, 999)
    assert "[auto]" in out
    assert "page 1/1" in out
    assert "(page has no records)" in r.list_records(9, 1)


def test_noop_diff_and_unknown_action(tmp_path):
    stage(tmp_path, "same", {
        "action": "replace", "target": "memory",
        "old_text": "same", "matched_entry": "same", "content": "same"
    })
    r = MagiReview(tmp_path)
    assert "(no textual difference)" in r.diff("same")
    assert "Unsupported/unknown action" in r._op_diff("x", {"action": "mystery"})


def test_dispatch_all_branches(tmp_path):
    stage(tmp_path, "d1", {"action": "add", "target": "memory", "content": "needle"})
    r = MagiReview(tmp_path)

    assert "Magi" in r.dispatch([])
    assert "Magi" in r.dispatch(["--help"])
    assert "Pending memory writes" in r.dispatch(["list"])
    assert "Usage: list" in r.dispatch(["list", "bad"])
    assert "Usage: show" in r.dispatch(["show"])
    assert "Pending memory write d1" in r.dispatch(["view", "d1"])
    assert "Usage: raw" in r.dispatch(["raw"])
    assert '"id": "d1"' in r.dispatch(["raw", "d1"])
    assert "Usage: diff" in r.dispatch(["diff"])
    assert "[add]" in r.dispatch(["diff", "d1"])
    assert "Usage: path" in r.dispatch(["path"])
    assert r.dispatch(["path", "d1"]).endswith("d1.json")
    assert "Usage: find" in r.dispatch(["find"])
    assert "d1" in r.dispatch(["search", "needle"])
    assert "Valid records: 1" in r.dispatch(["stats"])
    assert "OK d1" in r.dispatch(["check", "d1"])
    assert "Unknown subcommand" in r.dispatch(["wat"])


def test_created_at_and_time_fallbacks(tmp_path):
    d = tmp_path / "pending" / "memory"
    d.mkdir(parents=True)
    data = {
        "id": "time1",
        "subsystem": "memory",
        "summary": "time",
        "origin": "foreground",
        "created_at": "not-a-time",
        "payload": {"action": "add", "target": "memory", "content": "x"},
    }
    (d / "time1.json").write_text(json.dumps(data), encoding="utf-8")
    r = MagiReview(tmp_path)
    out = r.show("time1")
    assert "Created: unknown" in out


def test_resolve_hermes_home(monkeypatch, tmp_path, hermes_home_context):
    override = tmp_path / "override"
    assert resolve_hermes_home(profile_name="default", override=str(override)) == override.resolve()

    process_home = tmp_path / "process"
    request_home = tmp_path / "request"
    monkeypatch.setenv("HERMES_HOME", str(process_home))
    token = hermes_home_context.set_hermes_home_override(request_home)
    try:
        assert resolve_hermes_home(profile_name="default") == request_home.resolve()
        assert resolve_hermes_home(profile_name="work") == request_home.resolve()
    finally:
        hermes_home_context.reset_hermes_home_override(token)
