---
name: classify-transactions
description: Review income, expense, transfer and loan classifications and post balanced accounting entries with GST evidence.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# Classify Transactions



Read `references/proactive-tax-review.md` during every transaction-use/classification review. Analyse available facts and apply verified ATO rules proactively; ask only for missing facts that change applicability, never ask the user to decide established GST/tax rules. Keep accounting category, business use, deductibility, GST treatment and missing amount evidence separate. Reuse confirmed facts and applicable prior decisions. Resolve known zero/outside-GST/no-credit treatments without leaving them pending for unrelated missing documents.

Read the imported bank transactions, invoices, payment matches and saved allocation results. Investigate ambiguous transactions using saved evidence first; ask only about unresolved factual ambiguities. Reuse confirmed supplier treatments only when applicable. Propose category, business/private amount and GST treatment with evidence; obtain confirmation before posting newly inferred classifications.

Save every inferred classification that needs the user's confirmation as a proposal, not only in the workbook: `scripts/accounting_store.py save-proposals --request <JSON>` with `{"proposals":[{"journal":<the full post-journal payload, including transaction_id>,"reason":"evidence and why"}]}`. Every proposal's `journal.gst` must carry `source`: a local ATO library quote `{"library":{"sha256":"...","page":n,"quote":"exact sentence from that page"}}` (the code rejects a quote that is not on the page), the official page you actually opened, `{"url":"https://www.ato.gov.au/...","section":"heading or paragraph","accessed":"YYYY-MM-DD"}` (ato.gov.au or legislation.gov.au only), or, when you could not open one, `{"verified":false,"note":"what failed"}`. Never cite a page you did not read. Look up each distinct treatment once per period (not per transaction) before proposing, and reuse that citation for every row with the same treatment. The citation is kept with the posted journal, shown in the review workbook and the BAS evidence, and any unverified source is a BAS blocker until rechecked. Proposals stay off the ledger and show as `proposals_awaiting_approval` in workflow-status. Saving again replaces a transaction's open proposal. List with `proposals --start --end`; `proposal-groups --start --end` groups them by payee for review in chat; `export-proposals --start --end` writes the standard editable review workbook and `apply-proposals-workbook --workbook <file>` applies its Decision column (only on the user's returned file). Only after the user's explicit approval, run `decide-proposals --request '{"approve":[ids],"reject":[ids],"note":"..."}'`; approval posts the saved journal, rejection returns the transaction for a new proposal.

Use `scripts/accounting_store.py post-journal --request <JSON>`. Resolve helper relative to this skill and pass `--db <chosen workspace>/db/accounting.db`. Money is integer cents. Every journal must balance. Chart: 1000 bank clearing, 1100 receivables, 1200 GST receivable, 1500 equipment, 2000 payables, 2100 GST payable, 2200 loans, 3000 capital/drawings, 4000 sales, 4900 other income, 5000 general expenses, 5100 utilities, 5200 travel, 5300 insurance.

Example confirmed cash sale:
```json
{"reference":"sale-unique-reference","date":"2026-07-01","description":"Customer payment","transaction_id":1,"lines":[{"account":"1000","debit_cents":11000},{"account":"4000","credit_cents":10000},{"account":"2100","credit_cents":1000}],"gst":{"label":"sale","gross_cents":11000,"gst_cents":1000,"status":"reviewed","attribution_date":"2026-07-01","evidence":"Verified source invoice and payment"}}
```
For purchases debit expense/asset and GST receivable, credit bank. Link `invoice_ids` for purchase GST evidence. Use label sale/purchase/sale_refund/purchase_refund/excluded/settlement. Use settlement only for evidenced GST-control settlements; excluded movements cannot change GST control balances. Refund inputs are positive amounts; reverse ledger direction, and the report subtracts refunded GST. The bank direction and GST control account must match the classification. Pending GST stays null and status pending. Zero-rated/exempt treatment needs evidence too.

Transfers/loans/capital use excluded with zero gross/GST; retain explanatory evidence. A transfer between two imported accounts is two corresponding movements whose bank-clearing entries net to zero; do not post either as income/expense. Private company expenses need a justified director-loan treatment rather than an assumed deduction.

For non-cash GST, verify the actual attribution date, source recognition and payment treatment; avoid a second GST item when a receivable/payable is settled. Reviewed cash GST needs the linked bank transaction. Cash partial payments use confirmed links and per-invoice GST caps. For a multi-invoice journal supply invoice_tax_allocations as a list of invoice_id/gst_cents objects summing to the journal GST. The engine prevents cumulative overclaiming. A complete ledger journal cannot mix sale and purchase GST.

Review current official ATO guidance before final tax treatment. Use `reverse-journal --request <JSON>` with id/reason for correction, then post replacement with a new reference. Print what was posted and what remains unresolved.

## Review workbook

Continue the user's latest Excel review when one exists. Read the saved workbook and its baseline/support records before changing it; preserve user edits, source values, stable transaction IDs/accounts, confirmations and exclusions. Do not launch a replacement HTML table or expose an Evidence column. Keep tax sources and reasons in supporting records keyed by ID/account, with concise treatment and actual missing evidence in the workbook Notes.

For a new review, save proposals first, then run `export-proposals --start --end`: it writes the standard workbook (Summary by payee group, Review with one row per proposal and editable Decision / New account / Note columns, hidden check column). Do not build a different workbook layout. Apply the user's returned file with `apply-proposals-workbook --workbook <file>`; rows edited after the proposal changed are skipped as stale and reported.

Save under the selected workspace's `output/YYYY-MM-DD/reports/` with a new filename. Check saved amounts, identities, formulas, controls and visible layout before delivery. Apply workbook edits only when requested: verify baseline/source evidence and identity, reject duplicate/missing IDs or stale source changes, use supported audited correction/posting commands and preserve existing confirmation requirements. Report applied versus pending changes and regenerate the affected workbook. If Excel cannot be produced, report the blocker; offer the existing fixed `review-table` renderer as an explicit fallback, never a silent default or redesigned HTML report.

## Accrual recognition and settlements

Read `references/accrual-workflow.md` for complete invoice/settlement examples. Use invoice_ids for sales as well as purchases so document completeness is visible. For accrual, post invoices to receivables/payables without requiring a bank link. Later payments settle those accounts with zero additional GST and confirmed payment links. The engine rejects a second live recognition of an accrual document; reverse and replace a mistaken recognition. Split recognition of one document is not supported by this version.

G1 uses GST-inclusive gross: for reviewed sales, gross_cents must reconcile to net sales/other-income lines plus GST. GST-free/input-taxed sales still use sale with evidenced zero GST, not excluded. Separate non-sales receipts into justified balance-sheet lines.
