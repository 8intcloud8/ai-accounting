---
name: prepare-bas
description: Produce an Australian Simpler BAS GST review workpaper from reviewed local ledger entries and list missing evidence.
---

# Prepare BAS

Resolve workspace, entity and reporting period. Read references/ato-guidance.md and refresh official guidance before tax treatment. Confirm registration and cash/accrual basis from the stored profile. The initial implementation covers Simpler BAS GST subtotals G1, 1A and 1B; PAYG and other labels need separate review.

Run `scripts/accounting_store.py prepare-bas --start YYYY-MM-DD --end YYYY-MM-DD`. The engine selects reviewed GST items by explicit attribution date, excludes reversed journals, subtracts refund adjustments, and saves immutable report snapshots plus dated JSON/CSV exports. Unknown/unreviewed items are blockers, not zero GST.

Present reviewed subtotals in dollars, pending items, reconciliation status and source references. Always identify output as a draft workpaper. `ready_for_review` means internal checks passed, not that a return has been lodged or professionally certified. Full BAS completion, special GST schemes and electronic lodgement are outside this version. Never turn partial subtotals into a final amount payable.

## Show the review table in Codex

Open the generated draft BAS CSV returned by the reporting helper. State its draft/not-ready status and blockers in chat before interpreting any subtotals. Zero reviewed subtotals must not be described as a nil BAS when classifications or evidence are incomplete.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review"` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Complete review exports

The helper returns saved_csv, saved_documents_csv and saved_exceptions_csv. BAS CSV includes entity, dates, currency, GST-inclusive G1 convention, ready_for_review, blockers and scope. Open the exceptions CSV first when blocked, then the document register for decisions, and the draft totals when useful. A zero subtotal with unresolved items is not a nil BAS. Do not mark review checkpoints complete while documents or account coverage are unresolved.
