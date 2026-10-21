---
name: manage-accounting
description: Continue a local accounting period, show saved progress and route to the next accounting plugin.
---

# Manage Accounting

Resolve the saved workspace and reporting dates. Run `scripts/accounting_store.py workflow-status --start YYYY-MM-DD --end YYYY-MM-DD` with `AI_ACCOUNTING_DB` pointing to the workspace database. Read the returned blockers; do not derive completion from chat history alone.

Route using the document-first workflow below: setup-accounting; search-bills/save-bills when wanted; extract-invoice and extract-bankstatement; classify-transactions and allocate-running-costs; match-payments and settlement classification; reconcile-accounts; prepare-bas; prepare-tax-report. Each is a separate plugin. Use available plugins; explain any missing installation.

Show a short completed/pending list and the next concrete action. Missing GST does not mean zero. Never count invoice plus its bank payment as two expenses. Bank transfers, director loans and repayments need explicit treatment.

After actual source/sales completeness checks and PAYG/tax-adjustment review, record the appropriate step with `complete-step --request <JSON>`, containing start, end, step and evidence. Allowed steps: source_completeness, sales_completeness, payg_review, tax_adjustments. Do not mark these complete merely to clear blockers. Data changes invalidate these review checkpoints automatically.

For corrections run `correct-record --request <JSON>` with kind invoice/payment/allocation, id and reason. Reverse linked journals first with `reverse-journal`. Invoice withdrawal preserves history and requires corrected reimport of the same source. Recompute reports after corrections. `backup-workspace --output <new.zip>` creates a consistent local snapshot; `restore-workspace --archive <zip> --destination <new folder>` restores for inspection. Never restore over a live workspace.

## Open the review CSV in Codex

Open the current stage’s review CSV before asking the user to decide. Route to the producing skill to create it if needed. Show one current review file at a time; do not open every historical export or unrelated period.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

After the file has been written and its path verified, call `open_in_codex` with `target: { type: "file", path: "<absolute CSV path>" }` and `placement: "right"` to open it beside this chat. Open the new file or the existing current review tab; avoid duplicate tabs. A file link alone does not satisfy opening when that tool is available. Give a short chat summary identifying the file, what to review and any outstanding decision. Only claim it opened when the tool confirms the outcome; if the tool is unavailable or opening fails, state that and provide a clickable absolute-path file link.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Document completeness and accrual workflow

After extraction, review every document independently of payment. For accrual GST, recognise bills and sales/RCTIs before or alongside matching; a missing payment does not exclude an unpaid invoice. Run workflow-status and inspect its documents list: recognised, deferred, excluded, unresolved or pending_gst. Opening a document is not recognition.

Use `review-document --request <JSON>` for period-specific decisions: invoice_id, start, end, status (excluded/deferred/unresolved), reason and, for deferred, review_after after the period end. Recognition derives from live journals. Retain source/payment timing and prior-claim evidence; never exclude documents merely to clear blockers. Source corrections invalidate decisions through their source hash. Deferred decisions apply only to that period and require review in later periods.

Route: setup and source inventory; import purchases, sales/RCTIs and all bank/card accounts; review document recognition, allocation and GST; match settlements without duplicate expenses/revenue; reconcile; resolve document/account/PAYG exceptions; prepare draft BAS. Cash and accrual have different timing; these are iterative passes rather than mandatory payment-first steps. Read classify-transactions references/accrual-workflow.md for entries.
