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

## Showing transactions

Whenever you show the user bank transactions (any list: "show me these", a payee group, the unclassified ones), run `export-transactions --start --end` with `--ids 12,15,...` for just those transactions (for the whole period, link the live `output/BAS live/<start> to <end>/BAS workbook.xlsx` instead: every change rewrites it). It writes an Excel workbook in `output/` with a Summary by payee and one row per transaction showing its status (Classified, Proposed, Not classified), category and GST. Give the user the workbook link, plus a short grouped summary in chat (count and total per payee group). Never paste a table of more than 10 transactions in chat. For proposals the user will approve in Excel, use `export-proposals` instead: its Decision column can be applied back.

## Keep working; stop only when you need the user

Work like Claude Code: do the work, keep going, and stop only when you need the user.

1. Commands that change the books return `next_step`. When `keep_going` is true, do `do_next` straight away, without asking permission, and carry on. When it is false, stop: say in a sentence or two what you did, ask everything you need in that one message (numbered, each with your best answer from the records), and make `end_your_reply_with` the last line, word for word. If a command returned none, run `workflow-status --start --end` and decide the same way.
2. Never show step numbers, step lists or progress summaries. The chat is the one place the user looks: results and decisions go there.
3. Ask only for what only the user can give: facts, missing documents, and the OK to post. Never ask "shall I…" for work you can do.

Never end a reply with a promise such as "I'll continue with…", "Next I'll…" or "I'll now…". Your turn has ended and nothing happens. Do that work now instead.

Never call anything pending, blocked, under review or unresolved without saying in the same sentence what resolves it and who does it, for example: "$2.73 OpenAI GST is pending: check the invoice; an ARN means no credit, an ABN means claim it." When posting GST as pending, `gst.resolve` must say exactly that; the command refuses pending GST without it.

When nothing is open, prepare the BAS draft and show it.

## Passing input to commands

Commands that take `--request`, `--records`, `--rule`, `--confirmed` or `--approved` read JSON from stdin when given `-`. Pipe the JSON in (`... --request - <<'JSON'` … `JSON`) instead of writing request files: every file you write is shown to the user as an edited file. Send several documents in one call where a command accepts a list, for example `record-supporting` with `{"documents": [...]}`.

## Personal-card supplier evidence links

When a confirmed personal-card bank debit paid an already recognised purchase, use `link-supplier-payments --request -` to record evidence only, separately from a company reimbursement. Request: `{"business_id":"...","account_id":"...","source_nickname":"...","confirmed_by":"user","reason":"actual verified supplier evidence and authorization","links":[{"transaction_id":1,"journal_id":2,"amount_cents":1100}]}`. Choose the recorded personal payment source; never change ownership to bypass matching controls. Allocate the complete bank debit across live reviewed purchase journals, within their gross amounts. Split service/surcharge journals explicitly and retain distinct equal-value bank occurrences. This creates audited links, no journals or new GST. Replaying identical links is idempotent. Use the same command with `"action":"unlink"` and the transaction/journal pairs to remove mistaken or stale links with a reason before replacement. A changed source or reversed journal invalidates classification. Verify workflow, workbook and dashboard plus unchanged GST/expense totals afterward. Never invent a reimbursement or duplicate journal merely to clear a status.

## Business, Personal and Shared purpose

Keep transaction purpose separate from company recognition and GST allocation. Use `review-transaction-purpose --request -` for explicit confirmed purpose corrections on a recorded personal source: business_id, account_id, source_nickname, start/end, confirmed_by=user, and records with transaction_id, purpose (Business/Personal/Shared), category, outside_bas boolean, and reason. Shared does not establish a business percentage or GST claim. Set outside_bas=true only when the user explicitly retains the payment outside this BAS; it closes purpose review without posting a company expense or GST. Existing postings or supplier links must be resolved before such exclusion. Changed source evidence invalidates the review. Do not infer a percentage or claim simply to clear a status. Export the workbook to show its Purpose column and refresh the dashboard purpose counts.
