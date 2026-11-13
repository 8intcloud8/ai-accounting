---
name: reconcile-accounts
description: Reconcile imported account movements against source statement opening and closing balances.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# Reconcile Accounts



Use source statements, imported transactions and posted classifications. Resolve the workspace and exact period; do not assume missing periods are complete. Inspect duplicates, omitted lines, refunds, transfers and unmatched documents.

Run `scripts/accounting_store.py reconcile-account --request <JSON>` with account, start/end ISO dates, signed opening_cents/closing_cents, and statement absolute path. Account names must match imported accounts. Statement evidence is preserved locally; opening plus credits minus debits must equal closing. For credit cards use a consistent signed balance convention, explaining it in the review.

Reconcile each account separately. A numerical balance match does not prove classification, tax eligibility or document completeness. Show unresolved items and run workflow-status. Added/changed transactions invalidate prior reconciliations through their digest. Never adjust a transaction merely to force a balance.

## Show the review table in Codex

Create and open a reconciliation-review CSV showing each account/period, opening balance, credits, debits, calculated closing, source closing, difference and verification status. Use explicit cents/AUD column labels. Distinguish independently printed statement balances from boundaries derived from transaction running balances.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/reports/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review"` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Evidence and coverage

Supply boundary_kind=statement only with independently checked statement opening/closing balances and boundary_evidence identifying their source/pages and quoting both balances as printed (e.g. "Statement p1: opening balance 1,000.00, closing balance 1,055.00"); evidence that does not quote them is refused. The opening balance must equal the previous period's reconciled closing balance for the same account. If the statement shows no balances, ask for another bank document that does (e.g. the previous statement's closing balance or an internet-banking balance export); never present a derived balance as the statement's. Otherwise use boundary_kind=derived; arithmetic can pass while BAS readiness remains blocked. Do not relabel reconstructed balances as independent evidence. `configure-reporting` records all expected account names; a missing account-period is a blocker.

Also inspect all unresolved documents, outstanding matches and ledger receivable/payable/GST control balances before completing source/sales review checkpoints. Arithmetic reconciliation is not a complete ledger audit. Zero-activity accounts currently need manual evidence and remain blocked by the helper; do not manufacture transactions to clear coverage.

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
