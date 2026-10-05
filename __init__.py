"""Hermes Memory Review plugin.

Read-only by design: this plugin never approves, rejects, edits, or deletes a
pending memory write. It only inspects <HERMES_HOME>/pending/memory/*.json.
"""

from __future__ import annotations

import argparse
from typing import List

from .core import MemoryReview, resolve_hermes_home, tokenize


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


def _setup_cli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "memory_review_args",
        nargs=argparse.REMAINDER,
        help="list|show|diff|raw|find|stats|verify|path ...",
    )


def register(ctx) -> None:
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
