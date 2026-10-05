"""Structured backend for Hermes Memory Review.

Hermes mounts this router below ``/api/plugins/memory-review`` and scopes the
request to the active profile. Pending-write decisions are delegated to Hermes'
native ``/memory`` command path through the documented Desktop Plugin SDK.
Stored-memory edits delegate persistence to Hermes' own ``MemoryStore``.
"""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


_PLUGIN_ID = "memory-review"
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_core = runpy.run_path(str(_PLUGIN_ROOT / "core.py"))
MemoryReview = _core["MemoryReview"]
resolve_hermes_home = _core["resolve_hermes_home"]

router = APIRouter()


class MemoryEditRequest(BaseModel):
    old_text: str
    content: str


def _settings() -> Dict[str, Any]:
    """Mirror PluginContext.get_config for this profile-scoped backend."""
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly() or {}
    except Exception:
        return {}

    plugins = config.get("plugins") if isinstance(config, dict) else None
    entries = plugins.get("entries") if isinstance(plugins, dict) else None
    entry = entries.get(_PLUGIN_ID) if isinstance(entries, dict) else None
    if not isinstance(entry, dict):
        return {}

    legacy = entry.get("config") if isinstance(entry.get("config"), dict) else {}
    settings = entry.get("settings") if isinstance(entry.get("settings"), dict) else {}
    return {**legacy, **settings}


def _review() -> Any:
    settings = _settings()
    home = resolve_hermes_home(
        profile_name="default",
        override=str(settings.get("home_override") or ""),
    )
    return MemoryReview(
        home=home,
        default_page_size=max(1, int(settings.get("default_page_size") or 20)),
        max_page_size=max(1, int(settings.get("max_page_size") or 100)),
    )


def _memory_store() -> Any:
    """Load the active profile's built-in memory with Hermes' native safeguards."""
    from tools.memory_tool import load_on_disk_store

    return load_on_disk_store()


def _memory_target(store: Any, target: str) -> Dict[str, Any]:
    if target not in {"memory", "user"}:
        raise HTTPException(status_code=400, detail="target must be 'memory' or 'user'.")
    entries = store.memory_entries if target == "memory" else store.user_entries
    return {
        "target": target,
        "count": len(entries),
        "entries": [{"index": index, "content": entry} for index, entry in enumerate(entries)],
    }


def _record_summary(record: Any) -> Dict[str, Any]:
    return {
        "id": record.id,
        "action": record.action,
        "target": record.target,
        "origin": record.origin,
        "summary": record.summary,
        "created_at": record.created_at,
    }


@router.get("/records")
def list_records() -> Dict[str, Any]:
    review = _review()
    records, issues = review._load()
    return {
        "count": len(records),
        "records": [_record_summary(record) for record in reversed(records)],
        "issues": issues,
    }


@router.get("/records/{selector}")
def record_detail(selector: str) -> Dict[str, Any]:
    review = _review()
    record, error = review._resolve(selector)
    if error:
        if error == "No pending memory writes.":
            error = f"No pending memory write with id/prefix {selector!r}."
        raise HTTPException(status_code=404, detail=error)
    assert record is not None
    return {
        "id": record.id,
        "record": _record_summary(record),
        "payload": record.payload,
        "proposal": review.show(record.id),
        "diff": review.diff(record.id),
        "raw": review.raw(record.id),
        "verify": review.verify(record.id),
    }


@router.get("/memory")
def stored_memory() -> Dict[str, Any]:
    store = _memory_store()
    return {
        "targets": {
            "memory": _memory_target(store, "memory"),
            "user": _memory_target(store, "user"),
        }
    }


@router.put("/memory/{target}")
def replace_stored_memory(target: str, body: MemoryEditRequest) -> Dict[str, Any]:
    if target not in {"memory", "user"}:
        raise HTTPException(status_code=400, detail="target must be 'memory' or 'user'.")

    store = _memory_store()
    result = store.replace(target, body.old_text, body.content, matched_entry=body.old_text)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result)

    return {
        "success": True,
        "result": result,
        "target": _memory_target(store, target),
    }
