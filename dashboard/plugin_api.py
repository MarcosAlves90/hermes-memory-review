"""Structured read backend for Hermes Memory Review.

Hermes mounts this router below ``/api/plugins/memory-review`` and scopes the
request to the active profile. The module intentionally exposes GET routes
only; Desktop decisions are delegated to Hermes' native ``/memory`` command
path through the documented Desktop Plugin SDK.
"""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException


_PLUGIN_ID = "memory-review"
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_core = runpy.run_path(str(_PLUGIN_ROOT / "core.py"))
MemoryReview = _core["MemoryReview"]
resolve_hermes_home = _core["resolve_hermes_home"]

router = APIRouter()


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
