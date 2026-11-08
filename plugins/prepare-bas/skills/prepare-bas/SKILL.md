---
name: prepare-bas
description: Produce an Australian Simpler BAS GST review workpaper from reviewed local ledger entries and list missing evidence.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/agent-harness.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# Prepare BAS



If direct web-fetch fails, follow that reference's browser fallback before declaring official guidance unavailable. For an advice-only or read-only assessment, do not run reporting or save commands that write accounting records; use supplied facts as assumptions and identify any unverified client facts.

Resolve workspace, entity and reporting period. Read references/ato-guidance.md and refresh official guidance before tax treatment. Confirm registration and cash/accrual basis from the stored profile. The initial implementation covers Simpler BAS GST subtotals G1, 1A and 1B; PAYG and other labels need separate review.

Run `scripts/accounting_store.py prepare-bas --start YYYY-MM-DD --end YYYY-MM-DD`. The engine selects reviewed GST items by explicit attribution date, excludes reversed journals, subtracts refund adjustments, and saves immutable report snapshots plus dated JSON/CSV exports. Unknown/unreviewed items are blockers, not zero GST.

Present reviewed subtotals in dollars, pending items, reconciliation status and source references. Always identify output as a draft workpaper. `ready_for_review` means internal checks passed, not that a return has been lodged or professionally certified. Full BAS completion, special GST schemes and electronic lodgement are outside this version. Never turn partial subtotals into a final amount payable.

## Show the review table in Codex

Open the generated draft BAS CSV returned by the reporting helper. State its draft/not-ready status and blockers in chat before interpreting any subtotals. Zero reviewed subtotals must not be described as a nil BAS when classifications or evidence are incomplete.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/reports/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review"` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Complete review exports

The helper returns saved_csv, saved_documents_csv and saved_exceptions_csv. BAS CSV includes entity, dates, currency, GST-inclusive G1 convention, ready_for_review, blockers and scope. Open the exceptions CSV first when blocked, then the document register for decisions, and the draft totals when useful. A zero subtotal with unresolved items is not a nil BAS. Do not mark review checkpoints complete while documents or account coverage are unresolved.

## Identify the BAS work required

Reuse saved period applicability. Route missing or stale applicability facts to `grill-me-tax`; it owns the period interview and persistence. Validate its saved results before reporting readiness; do not repeat the interview here.

## Fixed HTML report contract

Use the bundled `review-table` renderer for every CSV review. Its fixed HTML
and controls live in `scripts/review_table.py` (canonical package source:
`accounting_core/review_table.py`). Do not generate a replacement HTML page,
invent a dashboard, rewrite CSS, or change layout between runs. Preserve the
renderer’s column order from the exported CSV, controls, labels, formatting,
source links and correction-request behaviour. Data, title, period, row counts,
issue messages and schema-required columns may change; presentation must not.
A different export schema may have different columns without a new design.

Open and verify the returned browser URL. Keep detailed results in that report;
chat should provide its link and any necessary action/blocker, not a duplicate
table. If the renderer fails, report the failure and link the saved CSV as an
explicit fallback; do not improvise another HTML design. Template changes require
an explicit implementation request and belong in the canonical source, followed
by release generation to synchronise bundled copies, never in per-run output.
