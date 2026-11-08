---
name: match-payments
description: Propose matches between stored invoices and bank payments, show outstanding invoices and unmatched debits, and save user-confirmed allocations for local accounting and BAS preparation.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/agent-harness.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# Match payments



Use shared local SQLite storage. Users do not configure a database. Retrieve records through the bundled helper at `scripts/accounting_store.py` (resolve relative to this skill directory).

1. Establish the business and bank account from existing user instructions or ask if unknown. Never match unrelated businesses/accounts. Both bank transactions and verified invoices must already be imported; report missing inputs.
2. Run `python3 <helper> match-payments --business "<ID>" --account "<ID>"`. Respect `AI_ACCOUNTING_DB` consistently. This command is read-only.
3. Populate the review report with candidates: invoice ID, supplier, invoice total/outstanding amount, transaction ID, bank date/description, proposed allocation, reasons, and ambiguity. Retrieve details using `invoices --business <ID>` and `transactions --account <ID>` if needed. Amounts are stored in cents; display currency and two decimals.
4. Matching uses currency, outstanding amount, invoice reference/supplier tokens, and dates within seven days before or ninety days after invoice date. These are proposals, not proof. Amount-only matches and candidates sharing invoices/payments must be flagged. Missing invoice dates/GST/currency remain unresolved. Confirmed allocations do not establish GST eligibility, business-use percentage or tax deductibility.
5. Ask the user to confirm concrete proposed allocations. Never convert a request to find matches into confirmation. Only after explicit user confirmation write an internal JSON payload:

```json
{"confirmed_by":"user","business_id":"business ID","account_id":"bank account ID","allocations":[{"invoice_id":1,"transaction_id":2,"amount_cents":3400}]}
```

Run `python3 <helper> confirm-payments --confirmed "<JSON path>"`. The command atomically validates identities/currency and remaining balances, preventing over-allocation. Exact confirmation replays are skipped; changed allocations require audited reversal through `correct-record` before replacement. Never fabricate user confirmation.

6. Partial payments use allocations below the invoice total. A combined bank payment can allocate to multiple invoices; multiple bank payments can allocate to one invoice. Present the whole allocation group for confirmation. These group combinations are manual proposals; the helper does not automatically search all combinations. No refunds, credit-note matching, currency conversion, or automatic correction are implemented. Explicit unmatching uses `correct-record` with kind payment, id and reason.
7. Report confirmed matches, remaining invoice balances, unallocated debits and unresolved cases. Use “unmatched/outstanding in records”, not “unpaid”: absent bank evidence does not prove nonpayment. A payment email or invoice receipt alone must not create a bank transaction or match. Keep invoice/receipt duplicate handling separate.

## Shared runtime

Use the Python executable at `<suite>/.venv/bin/python` when installed, otherwise the host Python 3.11+ runtime. Source files are copied into the workspace documents directory and hash verified. Relative evidence paths survive moving the complete workspace. The canonical runtime is maintained once in `accounting_core/` and bundled automatically for standalone plugins.

## Show the review table in Codex

Create a payment-match-review CSV from the actual proposal result before asking for confirmation. Include invoice/transaction IDs, supplier, bank date/description, currency, proposed_amount_cents, match reasons and pending/proposed/confirmed status. Include unresolved candidates distinctly; never label a proposal confirmed because the CSV was opened. If the engine returns no candidates, show that fact; any manually proposed pair must be clearly labelled manual and retain its unresolved issues.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/reports/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review"` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Sales receipts and settlements

The helper supports purchase payments and sale receipts according to the imported document role. Confirm the role and direction first. Credit-note refunds still require explicit review rather than automatic matching. Matching creates links only. For accrual, subsequent posting settles receivables/payables; do not recognise the original invoice again. Partial and grouped matches must reconcile to the selected bank movement. Unpaid documents remain in document review.

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

Personal-card purchases belong in expense claims. Match a company reimbursement
to its claim using record-purchase action reimburse, not to the supplier invoice.
Use the existing payment reference when linking a previously recorded reimbursement.

## Expense-claim ownership

Own payment-source and expense-claim state through record-purchase: set-source, approve, confirm-unreimbursed and reimburse. Inspect the bundled helper schema before constructing requests. Require actual user confirmation and evidence for each mutation. Keep supplier payment separate from company reimbursement. Reuse stable reimbursement references; link bank debits without recording the payment twice. These actions do not post journals; route posting to classify-transactions. Return saved claim fields to invoice reports.
