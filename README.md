# Hermes Memory Review 1.2.0

Read-only Hermes plugin for inspecting pending memory proposals in full when
`/memory pending` only exposes the short staged summary.

## Desktop

Version 1.2.0 adds a native **Memory Review** page to Hermes Desktop. After the
plugin is installed, enable both halves independently:

1. Enable the Agent plugin for the active profile under **Capabilities → Plugins**.
2. Enable the Desktop **Memory Review** plugin in the same Plugins screen.
3. Open **Memory Review** from the Desktop sidebar.

The page lists pending writes, supports local search and refresh, and provides
the same **Proposal**, **Diff**, **Raw**, and **Verify** read-only views as the
session/CLI commands. It polls every five seconds so changes remain visible even
when a live plugin socket is unavailable.

## Commands

Session:

```text
/memory-review list [page] [limit]
/memory-review show <id|prefix|oldest|newest>
/memory-review diff <id|prefix|oldest|newest>
/memory-review raw <id|prefix|oldest|newest>
/memory-review find <text>
/memory-review stats
/memory-review verify [id|all]
/memory-review path <id|prefix>
/memory-show <id|prefix>
/memreview ...
```

Terminal:

```bash
hermes memory-review list
hermes memory-review show newest
hermes memory-review diff <id> | less
hermes memory-review raw <id> | less
hermes memory-review verify all
```

Use the terminal form for very large payloads because messaging platforms may
impose their own message limits.

## Install

```bash
hermes plugins install https://github.com/MarcosAlves90/hermes-memory-review
hermes plugins enable memory-review
```

For Desktop, use **Capabilities → Plugins → Rescan** if the app was already
open, then enable the Desktop half separately. Hermes keeps the Agent and
Desktop enable switches independent by design.

## Local verification

```bash
./verify.sh
```

This checks Python syntax, runs the test suite, and enforces Cobertura line
coverage above 95%, then runs the same `hermes plugins validate --install-deps`
admission check used by the Hermes catalog. Test dependencies are isolated by
`uv`; the installed plugin itself uses Hermes plus the Python standard library.

## Safety model

The plugin is intentionally read-only. It reads only pending JSON records under
the active profile's `pending/memory` directory. It never calls memory approval
or rejection paths and never edits `MEMORY.md`, `USER.md`, or staged records.
Rendered strings escape terminal control, ANSI, and bidi-control characters.

Native Hermes remains responsible for mutations:

```text
/memory approve <id>
/memory reject <id>
```

## POLIS

Version 1.2.0 is developed under a strict POLIS V6.10.0 `feature` contract with
captured Red→Green proof, complete tests, and Cobertura coverage above 95%.
