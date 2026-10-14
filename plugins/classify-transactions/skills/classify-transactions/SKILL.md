---
name: classify-transactions
description: Review income, expense, transfer and loan classifications and post balanced accounting entries with GST evidence.
---

# Classify Transactions

Read the imported bank transactions, invoices, payment matches and saved allocation results. Ask about ambiguous transactions. Reuse confirmed supplier treatments only when applicable. Propose category, business/private amount and GST treatment with evidence; obtain confirmation before posting newly inferred classifications.

Use `scripts/accounting_store.py post-journal --request <JSON>`. Resolve helper relative to this skill and reuse AI_ACCOUNTING_DB. Money is integer cents. Every journal must balance. Chart: 1000 bank clearing, 1100 receivables, 1200 GST receivable, 1500 equipment, 2000 payables, 2100 GST payable, 2200 loans, 3000 capital/drawings, 4000 sales, 4900 other income, 5000 general expenses, 5100 utilities, 5200 travel, 5300 insurance.

Example confirmed cash sale:
```json
{"reference":"sale-unique-reference","date":"2026-07-01","description":"Customer payment","transaction_id":1,"lines":[{"account":"1000","debit_cents":11000},{"account":"4000","credit_cents":10000},{"account":"2100","credit_cents":1000}],"gst":{"label":"sale","gross_cents":11000,"gst_cents":1000,"status":"reviewed","attribution_date":"2026-07-01","evidence":"Verified source invoice and payment"}}
```
For purchases debit expense/asset and GST receivable, credit bank. Link `invoice_ids` for purchase GST evidence. Use label sale/purchase/sale_refund/purchase_refund/excluded/settlement. Use settlement only for evidenced GST-control settlements; excluded movements cannot change GST control balances. Refund inputs are positive amounts; reverse ledger direction, and the report subtracts refunded GST. The bank direction and GST control account must match the classification. Pending GST stays null and status pending. Zero-rated/exempt treatment needs evidence too.

Transfers/loans/capital use excluded with zero gross/GST; retain explanatory evidence. A transfer between two imported accounts is two corresponding movements whose bank-clearing entries net to zero; do not post either as income/expense. Private company expenses need a justified director-loan treatment rather than an assumed deduction.

For non-cash GST, verify the actual attribution date, source recognition and payment treatment; avoid a second GST item when a receivable/payable is settled. Reviewed cash GST needs the linked bank transaction. Cash partial payments use confirmed links and per-invoice GST caps. For a multi-invoice journal supply invoice_tax_allocations as a list of invoice_id/gst_cents objects summing to the journal GST. The engine prevents cumulative overclaiming. A complete ledger journal cannot mix sale and purchase GST.

Review current official ATO guidance before final tax treatment. Use `reverse-journal --request <JSON>` with id/reason for correction, then post replacement with a new reference. Print what was posted and what remains unresolved.
