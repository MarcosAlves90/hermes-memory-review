# Hermes Memory Review 1.1.0

Read-only Hermes plugin for inspecting pending memory proposals in full when
`/memory pending` only exposes the short staged summary.

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
unzip hermes-memory-review-1.1.0-polis-v6.10.0.zip
cd hermes-memory-review-1.1.0
./install.sh
```

For a named/custom Hermes profile:

```bash
./install.sh --home "$HOME/.hermes/profiles/<profile>"
```

After installation, restart or reload the long-running Hermes process.

## Local verification

```bash
./verify.sh --unit
```

This checks Python syntax, runs the test suite, and enforces Cobertura line
coverage above 95%.

Development verification requires `pytest` and `coverage.py`; the installed plugin itself uses only the Python standard library plus Hermes.

If the `hermes` executable is installed:

```bash
./verify.sh
```

also runs `hermes plugins doctor memory-review --ci`.

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

Version 1.1.0 is prepared as a planned POLIS V6.10.0
`behavior_preserving` release with strict tests and coverage. See
`polis/VALIDATION.md`. The distribution wrapper also includes external,
machine-readable POLIS evidence and the verified `.polis` artifact.

The runtime plugin implementation is byte-identical to the locked 1.0.0
baseline; this release hardens validation, release metadata, and handoff
documentation.
