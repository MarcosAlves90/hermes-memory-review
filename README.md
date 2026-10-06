# Hermes Memory Review 1.5.0

Hermes plugin for reviewing pending memory proposals and maintaining the
built-in Hermes `MEMORY.md` and `USER.md` stores from Hermes Desktop.

## Desktop

Version 1.5.0 provides a native **Memory Review** page in Hermes Desktop. After the
plugin is installed, enable both halves independently:

1. Enable the Agent plugin for the active profile under **Capabilities → Plugins**.
2. Enable the Desktop **Memory Review** plugin in the same Plugins screen.
3. Open **Memory Review** from the Desktop sidebar.

Use the top switch to alternate between **Pending writes** and **Stored memory**.
Pending writes support local search and refresh, and open on a
formatted **Overview** that presents metadata and proposed changes as readable
fields. **Proposal**, **Diff**, **Raw**, and **Verify** remain available for
technical inspection. Each pending write can be approved or rejected in place;
**Approve all** and **Reject all** require an explicit confirmation click. It
polls every five seconds so changes remain visible even when a live plugin socket
is unavailable.

**Stored memory** exposes separate **Memory** (`MEMORY.md`) and **User**
(`USER.md`) views. Every stored entry is listed and searchable. Select an entry,
edit its complete text, and choose **Save changes** to replace that exact entry.
The backend delegates the write to Hermes' own `MemoryStore`, so locking, limits,
content scanning, drift detection, and atomic persistence remain enforced by
Hermes. Both targets also show an approximate token footprint using Hermes'
`estimate_tokens_rough` helper.

Choose **Compact with AI** on either target to ask Hermes' active/default model
for a leaner representation. The model receives the current entries as untrusted
data and is instructed to preserve distinct facts, preferences, constraints,
decisions, names, identifiers, relationships, dates, workflow details, and other
important nuance while removing repetition and excess wording. The result is
shown as a preview with the before/after token estimate and model attribution.
Nothing is written until **Apply compaction** is selected. Applying verifies that
the source entries have not changed since the preview and then performs one
atomic `MemoryStore.apply_batch()` update.

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
/memory-compact-preview <memory|user>
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

## Mutation paths

For pending proposals, the backend reads JSON records under the active profile's
`pending/memory` directory. Desktop approve/reject buttons do not edit those
files directly: they call the documented Hermes Desktop SDK gateway path and
execute Hermes' native `/memory approve|reject <id|all>` commands.

For stored memory, the plugin backend exposes profile-scoped `GET /memory`,
`PUT /memory/{target}`, and `POST /memory/{target}/compact` routes. The GET route
reports Hermes' rough token estimate for each target. The PUT route loads Hermes'
on-disk store with
`tools.memory_tool.load_on_disk_store()` and calls `MemoryStore.replace()` with
the complete original entry pinned as the reviewed match. The plugin never
rewrites `MEMORY.md` or `USER.md` directly, so a stale, invalid, over-budget, or
blocked replacement is rejected by Hermes instead of silently overwriting newer
state.

AI preview generation runs through the plugin command context and
`ctx.llm.complete_structured()` without a provider or model override, so Hermes
keeps provider selection, credentials, fallback, and the active/default model.
The preview carries a fingerprint of the exact source entries. The compact POST
route rejects a stale fingerprint and delegates the complete consolidation to a
single `MemoryStore.apply_batch()` transaction; failed validation leaves the
store unchanged.

The equivalent native commands are:

```text
/memory approve <id>
/memory reject <id>
```

## POLIS

Version 1.5.0 is validated under a strict POLIS V6.10.0 `feature` contract,
complete tests, Cobertura coverage above 95%, and Hermes plugin validation.
