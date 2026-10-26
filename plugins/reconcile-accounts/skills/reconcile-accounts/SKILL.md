---
name: reconcile-accounts
description: Reconcile imported account movements against source statement opening and closing balances.
---

# Reconcile Accounts

Use source statements, imported transactions and posted classifications. Resolve the workspace and exact period; do not assume missing periods are complete. Inspect duplicates, omitted lines, refunds, transfers and unmatched documents.

Run `scripts/accounting_store.py reconcile-account --request <JSON>` with account, start/end ISO dates, signed opening_cents/closing_cents, and statement absolute path. Account names must match imported accounts. Statement evidence is preserved locally; opening plus credits minus debits must equal closing. For credit cards use a consistent signed balance convention, explaining it in the review.

Reconcile each account separately. A numerical balance match does not prove classification, tax eligibility or document completeness. Show unresolved items and run workflow-status. Added/changed transactions invalidate prior reconciliations through their digest. Never adjust a transaction merely to force a balance.

## Show the review table in Codex

Create and open a reconciliation-review CSV showing each account/period, opening balance, credits, debits, calculated closing, source closing, difference and verification status. Use explicit cents/AUD column labels. Distinguish independently printed statement balances from boundaries derived from transaction running balances.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review"` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Evidence and coverage

Supply boundary_kind=statement only with independently checked statement opening/closing balances and boundary_evidence identifying their source/pages. Otherwise use boundary_kind=derived; arithmetic can pass while BAS readiness remains blocked. Do not relabel reconstructed balances as independent evidence. `configure-reporting` records all expected account names; a missing account-period is a blocker.

Also inspect all unresolved documents, outstanding matches and ledger receivable/payable/GST control balances before completing source/sales review checkpoints. Arithmetic reconciliation is not a complete ledger audit. Zero-activity accounts currently need manual evidence and remain blocked by the helper; do not manufacture transactions to clear coverage.
