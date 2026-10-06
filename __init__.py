"""Hermes Memory Review plugin.

Pending-memory inspection stays read-only in this module. Stored-memory edits
and compaction writes are delegated to Hermes MemoryStore safeguards.
"""

from __future__ import annotations

import argparse
import json
from typing import List

from .core import (
    MEMORY_CHARS_PER_TOKEN,
    TOKEN_ESTIMATE_METHOD,
    MemoryReview,
    build_memory_compaction_preview,
    estimate_memory_tokens,
    memory_source_fingerprint,
    resolve_hermes_home,
    tokenize,
)
from .runtime_bridge import bind_plugin_context, clear_plugin_context


_MEMORY_CHARS_PER_TOKEN = MEMORY_CHARS_PER_TOKEN
_TOKEN_ESTIMATE_METHOD = TOKEN_ESTIMATE_METHOD


def _review(ctx) -> MemoryReview:
    override = ""
    default_page_size = 20
    max_page_size = 100
    try:
        override = ctx.get_config("home_override", default="") or ""
        default_page_size = int(ctx.get_config("default_page_size", default=20) or 20)
        max_page_size = int(ctx.get_config("max_page_size", default=100) or 100)
    except Exception:
        pass

    home = resolve_hermes_home(
        profile_name=getattr(ctx, "profile_name", "default") or "default",
        override=override,
    )
    return MemoryReview(
        home=home,
        default_page_size=max(1, default_page_size),
        max_page_size=max(1, max_page_size),
    )


def _dispatch(ctx, args: List[str]) -> str:
    return _review(ctx).dispatch(args)


def _slash(ctx, raw_args: str) -> str:
    try:
        args = tokenize(raw_args)
    except ValueError as exc:
        return f"Invalid arguments: {exc}"
    return _dispatch(ctx, args)


def _memory_show(ctx, raw_args: str) -> str:
    try:
        args = tokenize(raw_args)
    except ValueError as exc:
        return f"Invalid arguments: {exc}"
    if not args:
        return "Usage: /memory-show <id|prefix|oldest|newest>"
    return _dispatch(ctx, ["show", args[0]])


def _memory_store():
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


def _estimate_tokens(text: str) -> float:
    return estimate_memory_tokens(text)


def _source_fingerprint(entries: List[str]) -> str:
    return memory_source_fingerprint(entries)


def _compact_preview(ctx, raw_args: str) -> str:
    target = raw_args.strip().lower()
    if target not in {"memory", "user"}:
        return json.dumps({"success": False, "error": "target must be 'memory' or 'user'."})
    store = _memory_store()
    entries = list(store.memory_entries if target == "memory" else store.user_entries)
    result = build_memory_compaction_preview(ctx.llm, target, entries, _entry_delimiter())
    return json.dumps(result, ensure_ascii=False)


def _setup_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "memory_review_args",
        nargs=argparse.REMAINDER,
        help="list|show|diff|raw|find|stats|verify|path ...",
    )


def register(ctx) -> None:
    bind_plugin_context(ctx)
    on_unload = getattr(ctx, "on_unload", None)
    if callable(on_unload):
        on_unload(lambda: clear_plugin_context(ctx))

    ctx.register_command(
        "memory-review",
        handler=lambda raw: _slash(ctx, raw),
        description="Inspect pending Hermes memory writes in full (read-only).",
        args_hint="[list|show|diff|raw|find|stats|verify|path] ...",
        argument_mode="text",
    )
    ctx.register_command(
        "memreview",
        handler=lambda raw: _slash(ctx, raw),
        description="Alias for /memory-review.",
        args_hint="[list|show|diff|raw|find|stats|verify|path] ...",
        argument_mode="text",
    )
    ctx.register_command(
        "memory-show",
        handler=lambda raw: _memory_show(ctx, raw),
        description="Show one complete pending memory proposal by id/prefix.",
        args_hint="<id|prefix|oldest|newest>",
        argument_mode="text",
    )
    ctx.register_command(
        "memory-compact-preview",
        handler=lambda raw: _compact_preview(ctx, raw),
        description="Generate a reviewable AI compaction preview for stored Memory or User memory using the active/default model.",
        args_hint="<memory|user>",
        argument_mode="text",
    )

    def _cli_handler(ns) -> None:
        args = list(getattr(ns, "memory_review_args", []) or [])
        print(_dispatch(ctx, args))

    ctx.register_cli_command(
        "memory-review",
        help="Inspect pending memory writes (read-only)",
        setup_fn=_setup_cli,
        handler_fn=_cli_handler,
        description="Full inspection of Hermes pending memory writes.",
    )
