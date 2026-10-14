---
name: extract-bankstatement
description: Process, extract, combine, or consolidate bank statements (CSV, Excel, or PDF) from multiple banks into one standardised CSV for a financial year. Trigger when the user asks to process bank statements, extract transactions from statements, combine or consolidate statements from multiple banks, mentions a "bankstatements folder", a financial year (e.g. FY25, FY25-AU), or asks to run extract-bankstatement.
---

# Extract Bank Statement

Combine bank statement files (CSV, Excel, PDF) from multiple banks into one standardised CSV with columns: `date, description, debit, credit, file`.

This skill orchestrates three subagents per file — `bank-mapper`, `bank-extractor`, `bank-validator` — in a review loop so each statement's quirks are handled correctly before being added to the combined output.

## Steps

**0. Read `instructions.md` first.** It contains saved facts and preferences (e.g. known counterparties, categorisation rules) from previous runs. Apply them silently — don't re-ask the user things already answered there.

**1. Establish the input folder before extraction.** Ask the user: "Which folder contains your bank statements?" Wait for their answer before scanning or extracting. If they already supplied a folder for this run, use it without asking again. Do not infer a folder from an attached file or scan all of Downloads. An explicit request to test a specific attached file can run that file alone; it does not establish the folder for future runs.

**2. Ask the user:** "Which financial year? (e.g. FY25-AU)"

**3. Install dependencies:**

```
pip install pdfplumber openpyxl --break-system-packages
```

**4. List and identify files.** List all CSV/Excel/PDF files in the folder. Identify which are actual bank statements — skip anything that's clearly an invoice, bill, or receipt (those aren't statements and belong to a different workflow).

**5. Run the mapper → extractor → validator loop for each statement file:**

- Call `bank-mapper` on the file → get a column mapping.
- Call `bank-extractor` with the file + mapping → get extracted rows.
- Call `bank-validator` with the file + mapping + rows → get a decision: `approved`, `remap`, or `re-extract`.
- If `remap`: go back to `bank-mapper` with the validator's feedback.
- If `re-extract`: go back to `bank-extractor` with the validator's feedback.
- If `approved`: keep the rows for the combined output.
- **Cap at 3 rounds total per file.** If still not approved after 3 rounds, skip the file and warn the user which file failed and why.

**6. Save approved records automatically.** SQLite is internal assistant memory; never ask the user to install, create, or manage a database. `scripts/accounting_store.py` creates `the selected workspace’s `db/accounting.db` (legacy fallback: `~/.ai-accounting/accounting.db`)` on the first approved import. All runs reuse that location; `AI_ACCOUNTING_DB` is an internal override for separate workspaces.

- Identify the bank account from verified source information. Reuse the same stable identifier across files and runs. If absent, ask which account the statement belongs to; never invent one or use the filename as account identity. Only AUD imports are currently supported; stop for other currencies.
- After the validator approves a file, save its rows as an internal JSON file with `decision: "approved"`, `rows: [...]`, and `issues: []`. Never label unvalidated rows approved.
- Import the full approved source rows (before financial-year filtering):

```sh
python3 scripts/accounting_store.py import --source "<original statement>" --approved "<approved JSON>" --account "<stable account ID>"
```

- The script validates every row before writing, saves amounts as integer cents, and atomically saves the source hash, import history, transactions, and source links. A failure must be reported; never claim data was saved if the command fails.
- Identical source reimports are skipped. Changed extracted rows for an already imported source require explicit correction; never delete old history to force reimport.
- Matching rows in a different source are ambiguous without bank transaction IDs. The script rejects the entire import for review instead of silently discarding legitimate payments. Repeated identical rows within one file are retained. Report the conflict; do not alter descriptions or account IDs to bypass it. Exact source reimports are safely skipped.
- Exclude generated CSV exports from source discovery. Preserve source files.
- Retrieve the deduplicated records for the requested financial-year dates and create a fresh CSV export. If the destination exists, choose a new filename; the exporter refuses to overwrite files:

```sh
python3 scripts/accounting_store.py export --account "<stable account ID>" --start "<YYYY-MM-DD>" --end "<YYYY-MM-DD>" --output "<folder>/<FY>.csv"
```

Omit `--account` only when exporting all imported accounts intentionally. Use `summary` for aggregate totals and `transactions` for relevant dated records in later conversations. Those commands are read-only and do not create missing storage. Do not add opening/closing balance claims to database summaries; use separately verified source balances.

**7. Print a summary directly in chat.** This is mandatory, including single-file tests. A file link or subagent JSON alone is not a completed response. The parent agent converts internal JSON into a readable summary:

- Folder processed (or filename for an explicitly requested single-file test).
- Transaction date range and transaction count.
- Total money out (debits), total money in (credits), and net movement (credits minus debits), formatted to two decimal places.
- Opening and closing balances when verified from the source; otherwise say unavailable.
- Reconciliation status and any skipped files, invalid rows, or unresolved issues. Do not claim reconciled without verified balances or source totals.
- A link to the saved CSV and its actual location.

For multiple files, also print a compact table with one row per file: filename, transaction count, total debit, total credit, balance status (`reconciled` / `not-available` / `mismatch`), followed by combined totals. Combined totals use the final deduplicated output. Summarise extraction results only; do not equate bank credits with taxable income or debits with deductible expenses.

## NAB transaction listings

The inspector and extractor automatically recognise text-based NAB Transaction Listing PDFs. They use printed column positions, retain continuation descriptions, and require summary totals and every running balance to reconcile. Map `Date`, `Details`, `Debits`, and `Credits` to the standard fields; dates use `%d %b %y`. Other PDF layouts still need independent validation.

## Shared runtime

Use the Python executable at `<suite>/.venv/bin/python` when installed, otherwise the host Python 3.11+ runtime. Source files are copied into the workspace documents directory and hash verified. Relative evidence paths survive moving the complete workspace. The canonical runtime is maintained once in `accounting_core/` and bundled automatically for standalone plugins.
