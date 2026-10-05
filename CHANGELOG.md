# Changelog

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
