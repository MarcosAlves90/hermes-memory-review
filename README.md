# Hermes Memory Review 1.3.0

Hermes plugin for reviewing pending memory proposals in full and resolving them
from Hermes Desktop through Hermes' native approval commands.

## Desktop

Version 1.3.0 provides a native **Memory Review** page in Hermes Desktop. After the
plugin is installed, enable both halves independently:

1. Enable the Agent plugin for the active profile under **Capabilities → Plugins**.
2. Enable the Desktop **Memory Review** plugin in the same Plugins screen.
3. Open **Memory Review** from the Desktop sidebar.

The page lists pending writes, supports local search and refresh, and opens on a
formatted **Overview** that presents metadata and proposed changes as readable
fields. **Proposal**, **Diff**, **Raw**, and **Verify** remain available for
technical inspection. Each pending write can be approved or rejected in place;
**Approve all** and **Reject all** require an explicit confirmation click. It
polls every five seconds so changes remain visible even when a live plugin socket
is unavailable.

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

## Decision path

The plugin backend remains read-only and reads pending JSON records under the
active profile's `pending/memory` directory. Desktop approve/reject buttons do
not edit those files directly: they call the documented Hermes Desktop SDK
gateway path and execute Hermes' native `/memory approve|reject <id|all>`
commands. Hermes core therefore remains responsible for applying or discarding
pending writes. Rendered strings are escaped by React and the existing inspector
continues sanitizing terminal/control/bidi characters in technical views.

The equivalent native commands are:

```text
/memory approve <id>
/memory reject <id>
```

## POLIS

Version 1.3.0 is validated under a strict POLIS V6.10.0 `feature` contract,
complete tests, Cobertura coverage above 95%, and Hermes plugin validation.
