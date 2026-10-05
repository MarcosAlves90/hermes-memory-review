import importlib.util
import json
import sys
from pathlib import Path

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
    assert "refetchInterval" in source
    assert "querySelector" not in source
    assert "document." not in source


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
    assert "Pending memory write abc123" in data["proposal"]
    assert "old" in data["diff"] and "new" in data["diff"]
    assert '"id": "abc123"' in data["raw"]
    assert "OK abc123" in data["verify"]


def test_backend_is_read_only(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    api = load_api()
    methods = set()
    for route in api.router.routes:
        methods.update(route.methods or set())
    assert methods <= {"GET"}


def test_backend_returns_not_found_for_unknown_record(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    api = load_api()
    response = client_for(api).get("/records/missing")
    assert response.status_code == 404
    assert response.json()["detail"] == "No pending memory write with id/prefix 'missing'."
