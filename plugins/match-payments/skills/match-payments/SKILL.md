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

## Open the review CSV in Codex

Create a payment-match-review CSV from the actual proposal result before asking for confirmation. Include invoice/transaction IDs, supplier, bank date/description, currency, proposed_amount_cents, match reasons and pending/proposed/confirmed status. Include unresolved candidates distinctly; never label a proposal confirmed because the CSV was opened. If the engine returns no candidates, show that fact; any manually proposed pair must be clearly labelled manual and retain its unresolved issues.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

After the file has been written and its path verified, call `open_in_codex` with `target: { type: "file", path: "<absolute CSV path>" }` and `placement: "right"` to open it beside this chat. Open the new file or the existing current review tab; avoid duplicate tabs. A file link alone does not satisfy opening when that tool is available. Give a short chat summary identifying the file, what to review and any outstanding decision. Only claim it opened when the tool confirms the outcome; if the tool is unavailable or opening fails, state that and provide a clickable absolute-path file link.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Sales receipts and settlements

The helper supports purchase payments and sale receipts according to the imported document role. Confirm the role and direction first. Credit-note refunds still require explicit review rather than automatic matching. Matching creates links only. For accrual, subsequent posting settles receivables/payables; do not recognise the original invoice again. Partial and grouped matches must reconcile to the selected bank movement. Unpaid documents remain in document review.
