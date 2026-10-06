# Changelog

## 1.5.5 — 2026-10-06

- Fixed AI compaction accepting proposals that exceeded the requested entry-count limit when Hermes/provider-side JSON Schema validation was unavailable or not enforced.
- Added plugin-side entry-count validation: over-count proposals automatically retry once with the exact violation called out, then fail closed if the model still exceeds the limit.
- Added **Add entry** for both `MEMORY.md` and `USER.md`, delegating validation and persistence to Hermes `MemoryStore.add`.
- Added exact-entry deletion for both targets through `MemoryStore.remove`, with a two-step **Delete entry** / **Confirm delete** Desktop flow.
- Added regression coverage for providers that ignore `maxItems`, add/delete success, stale/native-store failures, and the new Desktop controls.

## 1.5.4 — 2026-10-06

- Fixed the AI compaction review layout so it is height-bounded, keeps its controls visible, scrolls proposed entries internally, and cannot cover the stored-memory editor below it.
- Changed compaction to treat the source as one memory corpus instead of preserving entry boundaries, with a dynamic schema cap that targets substantially fewer output entries.
- Reworked the compaction prompt around the durable, actionable core and explicitly removes examples, explanations, narrative history, temporary state, repeated qualifiers, and low-value nuance.
- Require at least 25% exact-character reduction before a proposal is accepted, with substantially tighter first-pass and retry budgets.
- Added preview metadata for source/output entry counts and actual percentage reduction.

## 1.5.3 — 2026-10-06

- Added visible in-progress feedback for AI compaction with an activity indicator and live elapsed time while Hermes is generating and validating the preview.
- Strengthened the compaction prompt with an explicit character budget, tighter compression guidance, and a preference for fewer entry-boundary overheads without dropping unique information.
- Added one automatic retry with a stricter target when the first AI proposal does not reduce the exact stored-memory character footprint.
- Changed compaction acceptance to the exact character footprint Hermes enforces; token counts remain informational estimates.

## 1.5.2 — 2026-10-06

- Fixed **Compact with AI** so preview generation no longer requires an open, active, or focused Hermes chat session.
- Moved Desktop preview requests to the plugin REST backend while preserving Hermes `ctx.llm` ownership of default-model routing, credentials, trust checks, and attribution.
- Kept preview generation non-mutating and retained stale-fingerprint validation plus one atomic `MemoryStore.apply_batch()` transaction for explicit application.

## 1.5.1 — 2026-10-06

- Fixed Stored memory token estimates to use Hermes' documented memory-budget scale of 2.75 chars/token instead of the generic model token estimator.
- Added exact character usage/limit and percentage used for both `memory` and `user`, using the active profile's configured MemoryStore limits.
- Aligned AI compaction before/after token estimates with the same Hermes memory-budget scale.

## 1.5.0 — 2026-10-06

- Added approximate token usage for both stored `memory` and `user` targets using Hermes' `estimate_tokens_rough` helper.
- Added **Compact with AI** using Hermes `ctx.llm` with the active/default provider and model, with no provider/model override.
- Added preview-first compaction with before/after token estimates, model attribution, proposed entries, and explicit **Apply compaction** / **Cancel preview** controls.
- Added stale-source fingerprint protection and atomic whole-target application through one `MemoryStore.apply_batch()` transaction.
- Added regression coverage for token metadata, default-model LLM routing, preview/apply separation, stale conflicts, and batch failures without real-memory mutation.

## 1.4.0 — 2026-10-05

- Added a top-level switch between pending writes and stored memory.
- Added Memory and User views that list every built-in `MEMORY.md` and `USER.md` entry with search and refresh.
- Added direct editing of existing stored entries from Desktop.
- Added structured stored-memory GET/PUT backend routes that delegate replacements to Hermes `MemoryStore` with the exact original entry pinned for stale-write protection.
- Preserved all v1.3 pending-review controls and native `/memory approve|reject` decision paths.

## 1.3.0 — 2026-10-05

- Added a formatted Overview as the default record view, with readable metadata and proposed content/change blocks.
- Added individual Approve and Reject controls backed by Hermes' documented `slash.exec` `/memory` command path.
- Added Approve all and Reject all with an explicit confirmation step before bulk mutation.
- Kept the plugin backend GET-only; Hermes core remains authoritative for applying or discarding staged memory writes.
- Added structured payload data to the detail endpoint for the Overview renderer.

## 1.2.0 — 2026-10-05

- Added a native Hermes Desktop **Memory Review** page and sidebar entry.
- Added profile-scoped, read-only backend routes for pending record lists and complete Proposal/Diff/Raw/Verify views.
- Added search, manual refresh, five-second polling fallback, empty/error states, and explicit backend-disabled guidance.
- Kept all memory mutations in Hermes core; the plugin backend exposes GET routes only.
- Added strict POLIS Red→Green coverage for the unified Desktop package and backend API.

## 1.1.0 — 2026-10-05

- Prepared and validated as a planned POLIS V6.10.0 behavior-preserving release.
- Added strict root-level validation with 24 tests and Cobertura coverage gate >95%.
- Fixed distribution verification so tests run from the package root.
- Added explicit POLIS validation contract and consumer handoff guidance.
- Runtime plugin implementation remains unchanged from 1.0.0.

## 1.0.0 — 2026-10-05

- `/memory-review` complete read-only inspector.
- `/memory-show` and `/memreview` convenience aliases.
- Terminal `hermes memory-review` surface.
- Full payload rendering, unified diffs, search, stats and validation.
- Exact/unique-prefix/oldest/newest selectors.
- Pagination.
- ANSI/control/bidi escaping.
- Profile-aware HERMES_HOME resolution with explicit override.
- Installer, uninstaller, verification script and unit tests.
