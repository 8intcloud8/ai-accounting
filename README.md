# AI Accounting

A local Codex accounting suite for Australian bookkeeping, BAS preparation and annual tax workpapers. Version 0.2.0-beta. macOS is the first supported installation target; other hosts are not yet certified.

## Install

### Codex Desktop (one click)

Open the Plugins Directory in Codex Desktop and add this repository (`8intcloud8/ai-accounting`) as a marketplace source. All 12 plugins are marked `INSTALLED_BY_DEFAULT`, so adding the marketplace is the only step — no per-plugin install clicks needed. Then ask: **“Set up AI Accounting for my business.”** Gmail connection for `search-email-invoices`/`save-invoices` is requested on first use, not at install time. Python 3.11+ must still be available on your machine; Email plugins also require Node/npm.

### Manual / other hosts

Download and extract a release into a permanent folder. Open it in Codex and ask: **“Set up AI Accounting for my business.”** Codex uses the setup-accounting skill to gather your workspace and business details, install dependencies, and register separate plugins. Python 3.11+ must be available from your computer or assistant host. Email plugins also require Node/npm and a connected Gmail account. The installer creates a private Python environment; SQLite needs no server or separate installation.

For an operator running setup directly:

```sh
python3 scripts/install.py --workspace "/path/to/Accounting" --profile profile.json --dependencies
```

Use `--local-only` for local statements and invoices without Gmail plugins. Profile fields: business_id, legal_name, entity_type (company/sole_trader/trust/partnership), gst_registered (true/false/null), gst_basis (cash/accrual/unknown). Unknown facts remain unknown. Open a new chat after installing.

## Separate plugins

| Plugin | Role |
|---|---|
| setup-accounting | Workspace and business setup |
| manage-accounting | Resume a period and show outstanding work |
| search-email-invoices | Find Gmail documents |
| save-invoices | Save selected documents |
| upload-invoices-drive | Store invoices in Google Drive invoices/YYYY-MM folders |
| extract-bankstatements | Extract/import bank transactions |
| extract-invoices | Extract/import invoice evidence |
| match-payments | Propose and confirm payment links |
| allocate-running-costs | Apply business-use allocations |
| classify-transactions | Post balanced ledger entries with GST evidence |
| reconcile-accounts | Reconcile statement opening/closing balances |
| prepare-bas | Draft G1/1A/1B GST workpaper |
| prepare-tax-report | Trial balance and annual accounting workpaper |

Each plugin has one skill. All reuse the same local workspace. Gmail search/save are optional. No Xero account is required.

## Workspace

```text
Accounting/
  db/accounting.db
  documents/<hash-prefix>/<hash>.<extension>
  output/YYYY-MM-DD/
  backups/
```

One business per workspace. Money uses integer cents. Imports retain source hashes; managed copies survive original-file moves. Move the complete workspace together and update the workspace selector when relocating it. CSV/JSON reports are for review; SQLite is internal assistant state.

Use `AI_ACCOUNTING_DB` to explicitly select a workspace database, or the installer-managed `accounting-workspace.json` in Codex home. Existing legacy installations keep their previous default unless explicitly configured.

## Corrections and backup

The workflow supports audited withdrawal/reimport of invoice extraction, reversing payment matches and allocations, and offsetting journal reversals. Reverse dependent records first. Source documents and correction history remain available. Report snapshots are historical; regenerate after changes. Workflow review checkpoints are invalidated when accounting data changes.

`backup-workspace` creates a consistent database/evidence ZIP; `restore-workspace` requires a new destination. Backup files contain private financial data. Keep them locally in a suitable location.

## Supported scope

This is a beta accounting workpaper product. It does not lodge BAS or income-tax returns. BAS output covers reviewed Simpler BAS GST subtotals only; PAYG/other labels and special GST schemes require additional work. Tax output is a bookkeeping workpaper, not tax payable or a complete statutory return. Accrual recognition requires reviewed entries and explicit attribution evidence. Opening balances and year-end adjustments must be entered before relying on full accounts. Cash partial payments use confirmed payment links and bounded per-invoice GST allocations. Multiple invoices in one journal require explicit invoice_tax_allocations. Mixed-use allocations must match the GST basis and attribution period.

## Development and release

`accounting_core/` is the sole maintained Python accounting runtime. `scripts/build_release.py` synchronizes it into the separate plugins, validates their one-skill structure and writes the local marketplace. Never edit generated runtime copies independently.

```sh
PYTHONPATH=accounting_core python3 -m unittest discover -s tests -v
python3 scripts/build_release.py --output /tmp/ai-accounting-release
```

Release builds must also build the two Node MCP plugins. CI runs storage/workflow tests on macOS and Linux, validates bundled parity, and tests Node plugins. Run fresh-install validation before public distribution. See docs/RELEASE-READINESS.md for remaining scope.

MIT licensed. Never commit private statements, invoices, credentials or database files.

## Review tables in Codex

Accounting skills show review CSVs as a local table beside the chat: search, sort, filter issues, read formatted amounts, open managed source documents and save check/correction requests. CSV exports remain available. The view runs only on this computer and needs no cloud service or additional Python package.

```sh
python3 accounting_core/accounting_store.py --db /path/to/accounting/db/accounting.db review-table --csv /path/to/accounting/output/YYYY-MM-DD/invoice-review.csv --title "Invoice review"
```

Open the returned review_url in Codex’s browser panel. Keep the command running while reviewing; stop it with Ctrl-C afterwards. Requests are saved as dated JSON workpapers with original row values and the CSV hash. Ask Codex to review and apply them through audited accounting commands. The table itself never edits SQLite or silently approves tax treatment. Source links serve only existing managed files under that workspace’s documents folder.

## Official guidance lookup

Every skill packages topic-specific official-source references. Before tax or regulatory decisions, Codex searches and reads applicable ATO guidance (or ASIC/Fair Work for the relevant obligations), cites exact URLs and access dates, and retains source notes with the draft workpaper. Failed access is disclosed and dependent treatment remains pending. Routine extraction and matching can continue.

Browsing/search is supplied by the host, not installed by this package. These instructions do not add a tax/payroll engine or a scheduled crawler. See [docs/OFFICIAL-GUIDANCE.md](docs/OFFICIAL-GUIDANCE.md) for routing, evidence records and observed source-access failures. Rebuild the suite to distribute changed references; existing installed caches are not updated by editing source files alone.
