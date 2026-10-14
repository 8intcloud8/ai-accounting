---
name: match-payments
description: Propose matches between stored invoices and bank payments, show outstanding invoices and unmatched debits, and save user-confirmed allocations for local accounting and BAS preparation.
---

# Match payments

Use shared local SQLite storage. Users do not configure a database. Retrieve records through the bundled helper at `scripts/accounting_store.py` (resolve relative to this skill directory).

1. Establish the business and bank account from existing user instructions or ask if unknown. Never match unrelated businesses/accounts. Both bank transactions and verified invoices must already be imported; report missing inputs.
2. Run `python3 <helper> match-payments --business "<ID>" --account "<ID>"`. Respect `AI_ACCOUNTING_DB` consistently. This command is read-only.
3. Print a concise table of candidates: invoice ID, supplier, invoice total/outstanding amount, transaction ID, bank date/description, proposed allocation, reasons, and ambiguity. Retrieve details using `invoices --business <ID>` and `transactions --account <ID>` if needed. Amounts are stored in cents; display currency and two decimals.
4. Matching uses currency, outstanding amount, invoice reference/supplier tokens, and dates within seven days before or ninety days after invoice date. These are proposals, not proof. Amount-only matches and candidates sharing invoices/payments must be flagged. Missing invoice dates/GST/currency remain unresolved. Confirmed allocations do not establish GST eligibility, business-use percentage or tax deductibility.
5. Ask the user to confirm concrete proposed allocations. Never convert a request to find matches into confirmation. Only after explicit user confirmation write an internal JSON payload:

```json
{"confirmed_by":"user","business_id":"business ID","account_id":"bank account ID","allocations":[{"invoice_id":1,"transaction_id":2,"amount_cents":3400}]}
```

Run `python3 <helper> confirm-payments --confirmed "<JSON path>"`. The command atomically validates identities/currency and remaining balances, preventing over-allocation. Exact confirmation replays are skipped; changed allocations require audited reversal through `correct-record` before replacement. Never fabricate user confirmation.

6. Partial payments use allocations below the invoice total. A combined bank payment can allocate to multiple invoices; multiple bank payments can allocate to one invoice. Present the whole allocation group for confirmation. These group combinations are manual proposals; the helper does not automatically search all combinations. No refunds, credit-note matching, currency conversion, or automatic correction are implemented. Explicit unmatching uses `correct-record` with kind payment, id and reason.
7. Print confirmed matches, remaining invoice balances, unallocated debits and unresolved cases. Use “unmatched/outstanding in records”, not “unpaid”: absent bank evidence does not prove nonpayment. A payment email or invoice receipt alone must not create a bank transaction or match. Keep invoice/receipt duplicate handling separate.

## Shared runtime

Use the Python executable at `<suite>/.venv/bin/python` when installed, otherwise the host Python 3.11+ runtime. Source files are copied into the workspace documents directory and hash verified. Relative evidence paths survive moving the complete workspace. The canonical runtime is maintained once in `accounting_core/` and bundled automatically for standalone plugins.
