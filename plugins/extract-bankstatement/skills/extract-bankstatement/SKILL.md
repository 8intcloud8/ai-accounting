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

**6. Write output.** Append all approved rows to `<folder>/<FY>.csv` (e.g. `bankstatements/FY25-AU.csv`). If the file already exists, append without duplicating rows already present. **Never move or delete the original source files.**

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
