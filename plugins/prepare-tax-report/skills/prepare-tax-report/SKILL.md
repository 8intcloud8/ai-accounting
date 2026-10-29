---
name: prepare-tax-report
description: Produce a local bookkeeping trial balance and income/expense workpaper for annual tax review.
---

# Prepare Tax Report

## Official guidance for tax and regulatory decisions

Read `references/official-sources.md` when this task requires tax or regulatory interpretation. Use live official guidance, cite exact sources and access dates, and report access failures explicitly. Routine extraction/matching does not establish GST or deduction eligibility.

Resolve entity and financial-year dates. Run `scripts/accounting_store.py tax-report --start YYYY-MM-DD --end YYYY-MM-DD` against the selected workspace. Show account balances, unresolved classifications and saved CSV/JSON.

This is an accounting workpaper, not a tax payable calculation or lodged return. Separately review capital assets/depreciation, non-deductible items, private use, reimbursements, losses and entity-specific tax adjustments using current ATO guidance. Keep company and individual returns distinct. Income-tax and GST timing can differ; do not relabel cash movements as accrual profit.

Do not claim a complete income statement or balance sheet without opening balances and all accrual/adjustment entries. Record tax_adjustments completion only after an actual documented review, and retain outstanding unsupported calculations explicitly.

## Show the review table in Codex

Open the generated annual accounting workpaper CSV returned by the helper. Explain its period, incomplete classifications and bookkeeping scope before asking for review; do not describe it as a complete tax return.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review"` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.
