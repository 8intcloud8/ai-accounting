---
name: prepare-bas
description: Produce an Australian Simpler BAS GST review workpaper from reviewed local ledger entries and list missing evidence.
---

# Prepare BAS

Resolve workspace, entity and reporting period. Read references/ato-guidance.md and refresh official guidance before tax treatment. Confirm registration and cash/accrual basis from the stored profile. The initial implementation covers Simpler BAS GST subtotals G1, 1A and 1B; PAYG and other labels need separate review.

Run `scripts/accounting_store.py prepare-bas --start YYYY-MM-DD --end YYYY-MM-DD`. The engine selects reviewed GST items by explicit attribution date, excludes reversed journals, subtracts refund adjustments, and saves immutable report snapshots plus dated JSON/CSV exports. Unknown/unreviewed items are blockers, not zero GST.

Present reviewed subtotals in dollars, pending items, reconciliation status and source references. Always identify output as a draft workpaper. `ready_for_review` means internal checks passed, not that a return has been lodged or professionally certified. Full BAS completion, special GST schemes and electronic lodgement are outside this version. Never turn partial subtotals into a final amount payable.

## Open the review CSV in Codex

Open the generated draft BAS CSV returned by the reporting helper. State its draft/not-ready status and blockers in chat before interpreting any subtotals. Zero reviewed subtotals must not be described as a nil BAS when classifications or evidence are incomplete.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

After the file has been written and its path verified, call `open_in_codex` with `target: { type: "file", path: "<absolute CSV path>" }` and `placement: "right"` to open it beside this chat. Open the new file or the existing current review tab; avoid duplicate tabs. A file link alone does not satisfy opening when that tool is available. Give a short chat summary identifying the file, what to review and any outstanding decision. Only claim it opened when the tool confirms the outcome; if the tool is unavailable or opening fails, state that and provide a clickable absolute-path file link.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Complete review exports

The helper returns saved_csv, saved_documents_csv and saved_exceptions_csv. BAS CSV includes entity, dates, currency, GST-inclusive G1 convention, ready_for_review, blockers and scope. Open the exceptions CSV first when blocked, then the document register for decisions, and the draft totals when useful. A zero subtotal with unresolved items is not a nil BAS. Do not mark review checkpoints complete while documents or account coverage are unresolved.
