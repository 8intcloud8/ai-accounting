# Beta validation — 14 October 2026

- 21 isolated Python tests passed: workspace installation/resume, schema upgrade, duplicate imports, source file/workspace moves, invoice corrections, audit history, journal reversal, balanced entries, cash partial-payment GST, mixed-use GST caps, profile guards, reconciliation, complete quarter workpaper, backup and restore.
- Search Bills: TypeScript check, production UI/server build and two asset-inlining regression tests passed.
- Save Invoices: TypeScript check, server build and two streaming/save regression tests passed.
- Both Node dependency audits report zero vulnerabilities after compatible updates and replacing the optional glob-filter dependency in the single-file build helper. Adapted helper retains its original MIT license.
- All 12 skill manifests validated. Canonical/runtime bundle parity checked.
- Independent Python review identified GST-control, duplicated evidence, source-kind, correction dependency and allocation-attribution issues; these were addressed with guards and regression coverage. A final independent re-review was unavailable due reviewer usage limits.

Tests used disposable synthetic businesses; the user's existing BAS database was not migrated or modified. The fresh-install test validates configuration/filesystem/CLI behaviour, not an interactive first-run Codex UI or live Gmail account. See RELEASE-READINESS.md for remaining public-release checks.
