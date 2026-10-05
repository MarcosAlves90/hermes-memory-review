from __future__ import annotations

import difflib
import json
import os
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


_BIDI_CONTROLS = {
    0x061C, 0x200E, 0x200F,
    *range(0x202A, 0x202F),
    *range(0x2066, 0x206A),
}


def tokenize(raw: str) -> List[str]:
    return shlex.split(raw or "", posix=True)


def resolve_hermes_home(profile_name: str = "default", override: str = "") -> Path:
    """Resolve the active profile without importing Hermes private modules.

    The documented standard layout is:
      default: ~/.hermes
      named:   ~/.hermes/profiles/<name>

    HERMES_HOME wins for the default profile, and for a named profile when its
    basename matches the active profile. `home_override` handles nonstandard
    multiplex/custom layouts explicitly.
    """
    if override and override.strip():
        return Path(override).expanduser().resolve()

    profile = (profile_name or "default").strip() or "default"
    env_home = (os.environ.get("HERMES_HOME") or "").strip()
    if env_home:
        env_path = Path(env_home).expanduser()
        if profile == "default" or env_path.name == profile:
            return env_path.resolve()

    root = Path.home() / ".hermes"
    if profile == "default":
        return root.resolve()
    return (root / "profiles" / profile).resolve()


def _safe_text(value: Any) -> str:
    text = "" if value is None else str(value)
    out: List[str] = []
    for ch in text:
        cp = ord(ch)
        if ch in ("\n", "\r", "\t"):
            out.append(ch)
        elif cp < 0x20 or cp == 0x7F or cp in _BIDI_CONTROLS:
            out.append(f"\\u{cp:04x}")
        else:
            out.append(ch)
    return "".join(out)


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, dict):
        return {_safe_text(k): _sanitize(v) for k, v in value.items()}
    return value


def _json(value: Any) -> str:
    return json.dumps(_sanitize(value), ensure_ascii=False, indent=2, sort_keys=False)


def _fmt_time(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value)).astimezone().isoformat(timespec="seconds")
    except Exception:
        return "unknown"


@dataclass(frozen=True)
class Record:
    path: Path
    data: Dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.data.get("id") or self.path.stem)

    @property
    def payload(self) -> Dict[str, Any]:
        value = self.data.get("payload")
        return value if isinstance(value, dict) else {}

    @property
    def action(self) -> str:
        return str(self.data.get("action") or self.payload.get("action") or "?")

    @property
    def target(self) -> str:
        return str(self.payload.get("target") or "?")

    @property
    def origin(self) -> str:
        return str(self.data.get("origin") or "foreground")

    @property
    def summary(self) -> str:
        return _safe_text(self.data.get("summary") or "")

    @property
    def created_at(self) -> float:
        try:
            return float(self.data.get("created_at", 0))
        except Exception:
            return 0.0


class MemoryReview:
    def __init__(self, home: Path, default_page_size: int = 20, max_page_size: int = 100):
        self.home = Path(home)
        self.pending_dir = self.home / "pending" / "memory"
        self.default_page_size = max(1, int(default_page_size))
        self.max_page_size = max(1, int(max_page_size))

    # ---------- storage ----------

    def _load(self) -> Tuple[List[Record], List[str]]:
        records: List[Record] = []
        issues: List[str] = []
        if not self.pending_dir.exists():
            return records, issues

        for path in sorted(self.pending_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(data, dict):
                    issues.append(f"{path.name}: root is {type(data).__name__}, expected object")
                    continue
                records.append(Record(path=path, data=data))
            except Exception as exc:
                issues.append(f"{path.name}: unreadable JSON ({_safe_text(exc)})")

        records.sort(key=lambda r: (r.created_at, r.id))
        return records, issues

    def _resolve(self, selector: str) -> Tuple[Optional[Record], Optional[str]]:
        records, _ = self._load()
        if not records:
            return None, "No pending memory writes."

        key = (selector or "").strip()
        if key == "oldest":
            return records[0], None
        if key == "newest":
            return records[-1], None

        exact = [r for r in records if r.id == key or r.path.stem == key]
        if len(exact) == 1:
            return exact[0], None

        pref = [r for r in records if r.id.startswith(key) or r.path.stem.startswith(key)]
        if len(pref) == 1:
            return pref[0], None
        if len(pref) > 1:
            ids = ", ".join(r.id for r in pref[:12])
            extra = "" if len(pref) <= 12 else f" (+{len(pref)-12} more)"
            return None, f"Ambiguous id prefix '{_safe_text(key)}': {ids}{extra}"
        return None, f"No pending memory write with id/prefix '{_safe_text(key)}'."

    # ---------- validation ----------

    @staticmethod
    def _validate_op(op: Any, where: str) -> Tuple[List[str], List[str]]:
        errors: List[str] = []
        warnings: List[str] = []
        if not isinstance(op, dict):
            return [f"{where}: operation must be an object"], warnings

        action = op.get("action")
        if action not in {"add", "replace", "remove"}:
            errors.append(f"{where}: unsupported action {action!r}")
            return errors, warnings

        if action == "add":
            if not isinstance(op.get("content"), str) or not op.get("content"):
                errors.append(f"{where}: add requires non-empty string content")
        elif action == "replace":
            if not isinstance(op.get("old_text"), str) or not op.get("old_text"):
                errors.append(f"{where}: replace requires non-empty old_text")
            if not isinstance(op.get("content"), str):
                errors.append(f"{where}: replace requires string content")
            if not op.get("matched_entry"):
                warnings.append(f"{where}: replace has no matched_entry pin")
        elif action == "remove":
            if not isinstance(op.get("old_text"), str) or not op.get("old_text"):
                errors.append(f"{where}: remove requires non-empty old_text")
            if not op.get("matched_entry"):
                warnings.append(f"{where}: remove has no matched_entry pin")
        return errors, warnings

    def validate_record(self, record: Record) -> Tuple[List[str], List[str]]:
        errors: List[str] = []
        warnings: List[str] = []
        d = record.data
        p = record.payload

        if d.get("subsystem") not in (None, "memory"):
            errors.append(f"subsystem is {d.get('subsystem')!r}, expected 'memory'")
        if not isinstance(d.get("payload"), dict):
            errors.append("payload is missing or is not an object")
            return errors, warnings
        if record.path.stem != record.id:
            warnings.append(f"filename id {record.path.stem!r} differs from record id {record.id!r}")
        if p.get("target") not in {"memory", "user"}:
            errors.append(f"target is {p.get('target')!r}, expected 'memory' or 'user'")

        action = p.get("action")
        if action == "batch":
            ops = p.get("operations")
            if not isinstance(ops, list) or not ops:
                errors.append("batch requires a non-empty operations list")
            else:
                for idx, op in enumerate(ops, 1):
                    e, w = self._validate_op(op, f"operations[{idx}]")
                    errors += e
                    warnings += w
        else:
            e, w = self._validate_op(p, "payload")
            errors += e
            warnings += w

        return errors, warnings

    # ---------- rendering ----------

    @staticmethod
    def _header(r: Record) -> str:
        return "\n".join([
            f"Pending memory write {r.id}",
            f"Action: {r.action}",
            f"Target: {r.target}",
            f"Origin: {r.origin}",
            f"Created: {_fmt_time(r.data.get('created_at'))}",
            f"Summary: {r.summary}",
        ])

    @staticmethod
    def _op_blocks(payload: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
        if payload.get("action") == "batch":
            ops = payload.get("operations") or []
            return [(f"operation {i}", op if isinstance(op, dict) else {"raw": op})
                    for i, op in enumerate(ops, 1)]
        return [("operation", payload)]

    @staticmethod
    def _op_diff(label: str, op: Dict[str, Any]) -> str:
        action = op.get("action")
        if action == "add":
            before, after = "", str(op.get("content") or "")
        elif action == "remove":
            before = str(op.get("matched_entry") or op.get("old_text") or "")
            after = ""
        elif action == "replace":
            before = str(op.get("matched_entry") or op.get("old_text") or "")
            after = str(op.get("content") or op.get("new_text") or "")
        else:
            return f"## {label}\nUnsupported/unknown action: {_safe_text(action)}\n{_json(op)}"

        before_lines = _safe_text(before).splitlines(keepends=True)
        after_lines = _safe_text(after).splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"{label}:before",
            tofile=f"{label}:after",
            lineterm="",
        ))
        if not diff:
            diff = "(no textual difference)"
        return f"## {label} [{_safe_text(action)}]\n{diff}"

    def help(self) -> str:
        return """\
Hermes Memory Review — read-only pending-memory inspector

Session commands:
  /memory-review list [page] [limit]      List pending writes (default)
  /memory-review show <id|prefix>         Full human-readable proposal
  /memory-review diff <id|prefix>         Before/after unified diff
  /memory-review raw <id|prefix>          Full sanitized JSON record
  /memory-review find <text>              Search summary + payload
  /memory-review stats                    Counts by action/target/origin
  /memory-review verify [id|all]          Structural/safety checks
  /memory-review path <id|prefix>         Show backing JSON path
  /memory-show <id|prefix>                Shortcut for show
  /memreview ...                          Alias

Selectors:
  exact id, unique id prefix, oldest, newest

Terminal:
  hermes memory-review <same subcommands>
  Example: hermes memory-review raw newest | less

This plugin never approves/rejects/changes memory. Use Hermes native:
  /memory approve <id>
  /memory reject <id>
"""

    def list_records(self, page: int = 1, limit: Optional[int] = None) -> str:
        records, issues = self._load()
        if not records and not issues:
            return f"No pending memory writes.\nDirectory: {self.pending_dir}"

        limit = self.default_page_size if limit is None else int(limit)
        limit = max(1, min(limit, self.max_page_size))
        page = max(1, int(page))
        start = (page - 1) * limit
        end = start + limit
        shown = records[start:end]
        pages = max(1, (len(records) + limit - 1) // limit)

        lines = [f"Pending memory writes ({len(records)}) — page {page}/{pages}:"]
        for r in shown:
            auto = " [auto]" if r.origin == "background_review" else ""
            lines.append(
                f"  {r.id}{auto}  {r.action}/{r.target}  {_fmt_time(r.data.get('created_at'))}"
            )
            lines.append(f"      {r.summary}")

        if not shown and records:
            lines.append("  (page has no records)")
        if issues:
            lines.append(f"\nSkipped malformed files: {len(issues)} (run `verify all` for details)")
        lines += [
            "",
            "Full proposal: /memory-review show <id>",
            "Diff:          /memory-review diff <id>",
            "Raw JSON:      /memory-review raw <id>",
        ]
        return "\n".join(lines)

    def show(self, selector: str) -> str:
        r, err = self._resolve(selector)
        if err:
            return err
        assert r is not None
        errors, warnings = self.validate_record(r)
        lines = [self._header(r), "", "Payload:", _json(r.payload)]
        if errors or warnings:
            lines += ["", f"Validation: {len(errors)} error(s), {len(warnings)} warning(s)"]
            lines += [f"  ERROR: {_safe_text(x)}" for x in errors]
            lines += [f"  WARN:  {_safe_text(x)}" for x in warnings]
        return "\n".join(lines)

    def raw(self, selector: str) -> str:
        r, err = self._resolve(selector)
        return err if err else _json(r.data)  # type: ignore[union-attr]

    def diff(self, selector: str) -> str:
        r, err = self._resolve(selector)
        if err:
            return err
        assert r is not None
        blocks = [self._op_diff(label, op) for label, op in self._op_blocks(r.payload)]
        return self._header(r) + "\n\n" + "\n\n".join(blocks)

    def path(self, selector: str) -> str:
        r, err = self._resolve(selector)
        return err if err else str(r.path)  # type: ignore[union-attr]

    def find(self, query: str) -> str:
        q = (query or "").casefold().strip()
        if not q:
            return "Usage: find <text>"
        records, issues = self._load()
        matches = []
        for r in records:
            haystack = (r.summary + "\n" + json.dumps(r.payload, ensure_ascii=False)).casefold()
            if q in haystack:
                matches.append(r)

        lines = [f"Matches for {_safe_text(query)!r}: {len(matches)}"]
        for r in matches[: self.max_page_size]:
            lines.append(f"  {r.id}  {r.action}/{r.target}  {r.summary}")
        if len(matches) > self.max_page_size:
            lines.append(f"  ... {len(matches) - self.max_page_size} more")
        if issues:
            lines.append(f"Skipped malformed files: {len(issues)}")
        return "\n".join(lines)

    def stats(self) -> str:
        records, issues = self._load()
        by_action: Dict[str, int] = {}
        by_target: Dict[str, int] = {}
        by_origin: Dict[str, int] = {}
        for r in records:
            by_action[r.action] = by_action.get(r.action, 0) + 1
            by_target[r.target] = by_target.get(r.target, 0) + 1
            by_origin[r.origin] = by_origin.get(r.origin, 0) + 1

        def fmt(d: Dict[str, int]) -> str:
            return ", ".join(f"{k}={v}" for k, v in sorted(d.items())) or "(none)"

        return "\n".join([
            f"Pending directory: {self.pending_dir}",
            f"Valid records: {len(records)}",
            f"Malformed files: {len(issues)}",
            f"Actions: {fmt(by_action)}",
            f"Targets: {fmt(by_target)}",
            f"Origins: {fmt(by_origin)}",
        ])

    def verify(self, selector: str = "all") -> str:
        records, storage_issues = self._load()
        lines: List[str] = []

        if selector == "all":
            selected = records
        else:
            r, err = self._resolve(selector)
            if err:
                return err
            selected = [r] if r else []

        total_errors = 0
        total_warnings = 0
        for r in selected:
            errors, warnings = self.validate_record(r)
            total_errors += len(errors)
            total_warnings += len(warnings)
            state = "ERROR" if errors else "WARN" if warnings else "OK"
            lines.append(f"{state} {r.id} ({r.action}/{r.target})")
            lines += [f"  ERROR: {_safe_text(x)}" for x in errors]
            lines += [f"  WARN:  {_safe_text(x)}" for x in warnings]

        if selector == "all":
            for issue in storage_issues:
                total_errors += 1
                lines.append(f"ERROR {_safe_text(issue)}")

        if not lines:
            lines.append("No pending memory writes to verify.")

        lines += [
            "",
            f"Result: {total_errors} error(s), {total_warnings} warning(s), "
            f"{len(selected)} record(s) checked.",
        ]
        return "\n".join(lines)

    # ---------- command dispatch ----------

    def dispatch(self, args: Sequence[str]) -> str:
        args = list(args)
        if not args or args[0].lower() in {"help", "-h", "--help"}:
            return self.help()

        cmd = args[0].lower()

        if cmd in {"list", "pending", "ls"}:
            try:
                page = int(args[1]) if len(args) > 1 else 1
                limit = int(args[2]) if len(args) > 2 else None
            except ValueError:
                return "Usage: list [page] [limit]"
            return self.list_records(page, limit)

        if cmd in {"show", "view"}:
            if len(args) < 2:
                return "Usage: show <id|prefix|oldest|newest>"
            return self.show(args[1])

        if cmd == "raw":
            if len(args) < 2:
                return "Usage: raw <id|prefix|oldest|newest>"
            return self.raw(args[1])

        if cmd == "diff":
            if len(args) < 2:
                return "Usage: diff <id|prefix|oldest|newest>"
            return self.diff(args[1])

        if cmd == "path":
            if len(args) < 2:
                return "Usage: path <id|prefix|oldest|newest>"
            return self.path(args[1])

        if cmd in {"find", "search"}:
            if len(args) < 2:
                return "Usage: find <text>"
            return self.find(" ".join(args[1:]))

        if cmd == "stats":
            return self.stats()

        if cmd in {"verify", "check"}:
            return self.verify(args[1] if len(args) > 1 else "all")

        return f"Unknown subcommand: {_safe_text(cmd)}\n\n{self.help()}"
