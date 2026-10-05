# Changelog

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
