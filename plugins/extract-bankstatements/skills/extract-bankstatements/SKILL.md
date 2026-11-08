---
name: extract-bankstatements
description: Process, extract, combine, or consolidate bank statements (CSV, Excel, or PDF) from multiple banks into a standardised CSV and editable Excel review workbook for the requested period. Trigger when the user asks to process bank statements, extract transactions from statements, combine or consolidate statements from multiple banks, mentions a "bankstatements folder", a financial year (e.g. FY25, FY25-AU), or asks to run extract-bankstatements.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# Extract Bank Statement



Read `references/proactive-tax-review.md` during every transaction-use/classification review. Analyse available facts and apply verified ATO rules proactively; ask only for missing facts that change applicability, never ask the user to decide established GST/tax rules. Keep accounting category, business use, deductibility, GST treatment and missing amount evidence separate. Reuse confirmed facts and applicable prior decisions. Resolve known zero/outside-GST/no-credit treatments without leaving them pending for unrelated missing documents.

Combine bank statement files (CSV, Excel, PDF) into a standardised CSV with columns: `date, description, debit, credit, file`, plus an editable `.xlsx` review workbook. Excel is the default user-facing review; retain CSV and local storage for source integrity.

This skill orchestrates three subagents per file — `bank-mapper`, `bank-extractor`, `bank-validator` — in a review loop so each statement's quirks are handled correctly before being added to the combined output.

## Steps

**0. Read `instructions.md` first.** It contains saved facts and preferences (e.g. known counterparties, categorisation rules) from previous runs. Apply them silently — don't re-ask the user things already answered there.

**1. Establish the input folder before extraction.** Ask the user: "Which folder contains your bank statements?" Wait for their answer before scanning or extracting. If they already supplied a folder for this run, use it without asking again. Do not infer a folder from an attached file or scan all of Downloads. An explicit request to test a specific attached file can run that file alone; it does not establish the folder for future runs.

**2. Reuse the requested reporting dates.** Ask for dates only when missing; a BAS quarter does not require a new financial-year question.

**3. Resolve dependencies:** Use the suite's isolated Python environment created by `scripts/install.py --dependencies`. For a standalone installation, create a dedicated virtual environment and install `pdfplumber` and `openpyxl` there. Never change system Python packages or use `--break-system-packages`. Reuse an existing compatible environment when available.

**4. List and identify files.** List all CSV/Excel/PDF files in the folder. Identify which are actual bank statements — skip anything that's clearly an invoice, bill, or receipt (those aren't statements and belong to a different workflow).

**5. Run the mapper → extractor → validator loop for each statement file:**

- Call `bank-mapper` on the file → get a column mapping.
- Call `bank-extractor` with the file + mapping → get extracted rows.
- Call `bank-validator` with the file + mapping + rows → get a decision: `approved`, `remap`, or `re-extract`.
- If `remap`: go back to `bank-mapper` with the validator's feedback.
- If `re-extract`: go back to `bank-extractor` with the validator's feedback.
- If `approved`: keep the rows for the combined output.
- **Cap at 3 rounds total per file.** If still not approved after 3 rounds, skip the file and warn the user which file failed and why.

**6. Save approved records automatically.** SQLite is internal assistant memory; never ask the user to install, create, or manage a database. `scripts/accounting_store.py` creates the selected workspace’s `db/accounting.db` (legacy fallback: `~/.ai-accounting/accounting.db`) on the first approved import. All runs reuse that location; `AI_ACCOUNTING_DB` is an internal override for separate workspaces.

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

**6a. Hand off transaction review.** After faithful import, use classify-transactions to enrich the saved transactions and create or continue the single review workbook. It owns business/private purpose, categories, GST proposals and applying workbook edits. Supply stable transaction IDs, complete source rows and validation results. Preserve every source transaction.

**7. Report extraction and personal/business review results.** Include the following in the Excel workbook; keep chat to the workbook link and necessary questions/blockers. The parent agent converts internal JSON into readable results:

- Folder processed (or filename for an explicitly requested single-file test).
- Transaction date range and transaction count.
- Total money out (debits), total money in (credits), and net movement (credits minus debits), formatted to two decimal places.
- Opening and closing balances when verified from the source; otherwise say unavailable.
- Reconciliation status and any skipped files, invalid rows, or unresolved issues. Do not claim reconciled without verified balances or source totals.
- Saved workbook and CSV locations.

For multiple files, also include a compact table in the report with one row per file: filename, transaction count, total debit, total credit, balance status (`reconciled` / `not-available` / `mismatch`), followed by combined totals. Combined totals use the final deduplicated output. Do not equate bank credits with taxable income or debits with deductible expenses.

## NAB transaction listings

The inspector and extractor automatically recognise text-based NAB Transaction Listing PDFs. They use printed column positions, retain continuation descriptions, and require summary totals and every running balance to reconcile. Map `Date`, `Details`, `Debits`, and `Credits` to the standard fields; dates use `%d %b %y`. Other PDF layouts still need independent validation.

## Shared runtime

Use the Python executable at `<suite>/.venv/bin/python` when installed, otherwise the host Python 3.11+ runtime. Source files are copied into the workspace documents directory and hash verified. Relative evidence paths survive moving the complete workspace. The canonical runtime is maintained once in `accounting_core/` and bundled automatically for standalone plugins.

## Review handoff

Use classify-transactions for the single versioned Excel review workbook and applying edits. Pass source counts, amounts, identities, exclusions and source-balance limitations. If unavailable, save the validated CSV and report classification/workbook creation as pending.
