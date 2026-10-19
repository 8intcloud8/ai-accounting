---
name: manage-accounting
description: Continue a local accounting period, show saved progress and route to the next accounting plugin.
---

# Manage Accounting

Resolve the saved workspace and reporting dates. Run `scripts/accounting_store.py workflow-status --start YYYY-MM-DD --end YYYY-MM-DD` with `AI_ACCOUNTING_DB` pointing to the workspace database. Read the returned blockers; do not derive completion from chat history alone.

Route in order: setup-accounting; search-bills/save-bills when email evidence is wanted; extract-invoice and extract-bankstatement; match-payments; allocate-running-costs; classify-transactions; reconcile-accounts; prepare-bas; prepare-tax-report. Each is a separate plugin. Use available plugins; explain any missing installation.

Show a short completed/pending list and the next concrete action. Missing GST does not mean zero. Never count invoice plus its bank payment as two expenses. Bank transfers, director loans and repayments need explicit treatment.

After actual source/sales completeness checks and PAYG/tax-adjustment review, record the appropriate step with `complete-step --request <JSON>`, containing start, end, step and evidence. Allowed steps: source_completeness, sales_completeness, payg_review, tax_adjustments. Do not mark these complete merely to clear blockers. Data changes invalidate these review checkpoints automatically.

For corrections run `correct-record --request <JSON>` with kind invoice/payment/allocation, id and reason. Reverse linked journals first with `reverse-journal`. Invoice withdrawal preserves history and requires corrected reimport of the same source. Recompute reports after corrections. `backup-workspace --output <new.zip>` creates a consistent local snapshot; `restore-workspace --archive <zip> --destination <new folder>` restores for inspection. Never restore over a live workspace.
