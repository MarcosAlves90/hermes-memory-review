"""Structured backend for Hermes Memory Review.

Hermes mounts this router below ``/api/plugins/memory-review`` and scopes the
request to the active profile. Pending-write decisions are delegated to Hermes'
native ``/memory`` command path through the documented Desktop Plugin SDK.
Stored-memory edits delegate persistence to Hermes' own ``MemoryStore``.
"""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any, Dict, List

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


class MemoryCompactionApplyRequest(BaseModel):
    source_fingerprint: str
    entries: List[str]


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


def _entry_delimiter() -> str:
    try:
        from tools.memory_tool_store import ENTRY_DELIMITER

        return ENTRY_DELIMITER
    except ModuleNotFoundError:
        return "\n§\n"


def _serialize_entries(entries: List[str]) -> str:
    return _entry_delimiter().join(entries)


def _estimate_tokens(text: str) -> int:
    try:
        from agent.model_metadata import estimate_tokens_rough

        return int(estimate_tokens_rough(text))
    except ModuleNotFoundError:
        return (len(text.encode("utf-8", "replace")) + 3) // 4 if text else 0


def _source_fingerprint(entries: List[str]) -> str:
    payload = json.dumps(list(entries), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _memory_target(store: Any, target: str) -> Dict[str, Any]:
    if target not in {"memory", "user"}:
        raise HTTPException(status_code=400, detail="target must be 'memory' or 'user'.")
    entries = store.memory_entries if target == "memory" else store.user_entries
    return {
        "target": target,
        "count": len(entries),
        "estimated_tokens": _estimate_tokens(_serialize_entries(list(entries))),
        "token_estimate_method": "estimate_tokens_rough",
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


@router.post("/memory/{target}/compact")
def apply_memory_compaction(target: str, body: MemoryCompactionApplyRequest) -> Dict[str, Any]:
    if target not in {"memory", "user"}:
        raise HTTPException(status_code=400, detail="target must be 'memory' or 'user'.")

    proposed = [entry.strip() for entry in body.entries]
    if not proposed or any(not entry for entry in proposed):
        raise HTTPException(status_code=400, detail="entries must contain at least one non-empty memory entry.")
    if len(set(proposed)) != len(proposed):
        raise HTTPException(status_code=400, detail="entries must not contain duplicates.")

    store = _memory_store()
    current = list(store.memory_entries if target == "memory" else store.user_entries)
    if not current:
        raise HTTPException(status_code=409, detail={"success": False, "error": "Stored memory is empty; there is nothing to compact."})
    if _source_fingerprint(current) != body.source_fingerprint:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "error": "Stored memory changed after this compaction preview was generated. Refresh and create a new preview.",
            },
        )

    operations = [
        {"action": "remove", "old_text": entry, "matched_entry": entry}
        for entry in current
    ] + [
        {"action": "add", "content": entry}
        for entry in proposed
    ]
    result = store.apply_batch(target, operations)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result)

    return {
        "success": True,
        "result": result,
        "target": _memory_target(store, target),
    }
