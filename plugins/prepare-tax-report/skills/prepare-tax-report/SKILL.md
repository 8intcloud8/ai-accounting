---
name: prepare-tax-report
description: Produce a local bookkeeping trial balance and income/expense workpaper for annual tax review.
---

# Prepare Tax Report

Resolve entity and financial-year dates. Run `scripts/accounting_store.py tax-report --start YYYY-MM-DD --end YYYY-MM-DD` against the selected workspace. Show account balances, unresolved classifications and saved CSV/JSON.

This is an accounting workpaper, not a tax payable calculation or lodged return. Separately review capital assets/depreciation, non-deductible items, private use, reimbursements, losses and entity-specific tax adjustments using current ATO guidance. Keep company and individual returns distinct. Income-tax and GST timing can differ; do not relabel cash movements as accrual profit.

Do not claim a complete income statement or balance sheet without opening balances and all accrual/adjustment entries. Record tax_adjustments completion only after an actual documented review, and retain outstanding unsupported calculations explicitly.

## Open the review CSV in Codex

Open the generated annual accounting workpaper CSV returned by the helper. Explain its period, incomplete classifications and bookkeeping scope before asking for review; do not describe it as a complete tax return.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

After the file has been written and its path verified, call `open_in_codex` with `target: { type: "file", path: "<absolute CSV path>" }` and `placement: "right"` to open it beside this chat. Open the new file or the existing current review tab; avoid duplicate tabs. A file link alone does not satisfy opening when that tool is available. Give a short chat summary identifying the file, what to review and any outstanding decision. Only claim it opened when the tool confirms the outcome; if the tool is unavailable or opening fails, state that and provide a clickable absolute-path file link.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.
