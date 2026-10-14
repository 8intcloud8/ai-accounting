---
name: reconcile-accounts
description: Reconcile imported account movements against source statement opening and closing balances.
---

# Reconcile Accounts

Use source statements, imported transactions and posted classifications. Resolve the workspace and exact period; do not assume missing periods are complete. Inspect duplicates, omitted lines, refunds, transfers and unmatched documents.

Run `scripts/accounting_store.py reconcile-account --request <JSON>` with account, start/end ISO dates, signed opening_cents/closing_cents, and statement absolute path. Account names must match imported accounts. Statement evidence is preserved locally; opening plus credits minus debits must equal closing. For credit cards use a consistent signed balance convention, explaining it in the review.

Reconcile each account separately. A numerical balance match does not prove classification, tax eligibility or document completeness. Show unresolved items and run workflow-status. Added/changed transactions invalidate prior reconciliations through their digest. Never adjust a transaction merely to force a balance.
