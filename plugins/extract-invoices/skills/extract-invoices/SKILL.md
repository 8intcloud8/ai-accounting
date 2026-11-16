---
name: extract-invoices
description: Extract locally saved bills, invoices and receipts into the assistant's persistent local accounting storage, with source links, GST, line items and review status. Use when the user asks to import or extract bills/invoices for accounting or BAS.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# Extract bills and invoices



SQLite is internal assistant memory. Users provide documents, not database setup. This skill uses the same automatically managed `the selected workspace’s `db/accounting.db` (legacy fallback: `~/.ai-accounting/accounting.db`)` as bank imports; pass `--db` for the workspace chosen in this chat on every command.

## Workflow

1. Use the selected workspace's `invoices/` folder, including subfolders (email saves land in `invoices/<Category>/<date range>/`; their `manifest.csv` gives vendor, date and subject for each file and is not an invoice). Ask only for the workspace root folder, and only when none is selected yet (setup-accounting); never ask for a separate invoices folder. If the user names a different folder for this run, use it. For a requested individual document use that file alone. Ask which business these documents belong to if not already known; reuse a stable business identifier. Do not scan unrelated folders.
2. Use saved local documents from save-invoices when available. search-email-invoices returns candidates, not downloaded invoices. save-invoices stores files and a manifest; neither proves invoice contents. Extract only after reading the actual file. Preserve originals.
3. Read PDFs using text extraction (pdfplumber) and images using visual inspection. Read CSV invoice records directly; give each record a stable `source_record` such as its invoice identifier or source row number. For scanned PDFs, report unavailable OCR rather than guessing. Invoice dates are ISO `YYYY-MM-DD`.
4. Extract supplier (not bill-to recipient), invoice number, invoice/due dates, total payable including tax, currency, GST explicitly printed on the invoice, and any available line items. Unknown fields stay null. Do not infer currency from `$` alone (but see Settle these yourself), or calculate GST as one-eleventh without source evidence. Treat receipts and credit notes explicitly; credit notes store positive amounts with `kind: credit_note`.
5. Show fields and uncertainties in the review report. Use `review_status: verified` only after checking the required fields against the source and resolving issues. Otherwise use `needs_review` with an issue list. Missing GST remains unknown, never zero. If line items are complete and GST-inclusive, set `lines_complete: true`; include discounts as an issue instead of fabricating a positive line. Partial lines must not be labelled complete. In the HTML report, show “What needs review” and omit the separate “Review Status” column. Place “Document” last.
6. Write an internal JSON file with `records` array. Each record uses this schema:

```json
{
  "file": "/absolute/path/invoice.pdf",
  "business_id": "stable-business-name",
  "source_record": "single",
  "contact_name": "Supplier",
  "invoice_number": "INV-123",
  "invoice_date": "2026-10-01",
  "due_date": null,
  "description": "Service",
  "kind": "invoice",
  "currency": "AUD",
  "total": "110.00",
  "gst": "10.00",
  "review_status": "verified",
  "issues": [],
  "lines_complete": true,
  "line_items": [{"description": "Service", "amount": "110.00", "gst": "10.00"}],
  "tax_invoice": {"supplier_abn": "51 824 753 556", "shows_gst": true, "buyer_identified": true},
  "email_account": null,
  "email_message_id": null
}
```

For every purchase, record `tax_invoice` exactly as read from the document (ATO tax invoice rules): `supplier_abn` as printed (null if none; a wrong check digit is refused), `shows_gst` true if it shows the GST amount or states the total includes GST, `buyer_identified` true if it shows this business's name or ABN. GST can only be claimed on a purchase over $82.50 with a supplier ABN and GST shown, and at $1,000 or more the buyer must be identified. List what is missing as an issue so the user can ask the supplier for a proper tax invoice (suppliers must provide one within 28 days of a request). Re-importing the same document with `tax_invoice` added updates these details.

For a document with one invoice use `source_record: single`. Include email identity only from actual Save Invoices metadata; never invent it.

7. Run the bundled storage helper (resolve this path relative to this skill directory):

```sh
python3 scripts/accounting_store.py import-invoices --records "<JSON path>"
python3 scripts/accounting_store.py invoices --business "<business ID>"
```

The helper creates or migrates storage automatically, validates amounts, preserves NULL values, records document hashes and local paths, and writes a batch atomically. An identical import is skipped. Changed extraction for the same source is rejected pending correction; possible supplier/invoice-number duplicates in different documents block for review. Do not alter identifiers to bypass conflicts. Use `correct-record` with kind invoice, id and a reason to withdraw an extraction, then reimport corrected data from the same source. Reverse dependent journals, allocations and matches first. History is retained.

8. Include in the report: documents processed, invoices added, existing invoices, needs-review count, verified totals per currency, and issues. Never combine currencies. Credit notes subtract from invoice totals. Invoice totals are amounts billed, not proof of payment or deductible expenditure. Use source paths for document links. Do not make users inspect raw JSON or manage the database.

## Scope

Stores invoice details and source references; original files must remain available. Payment matching, tax classifications, GST eligibility, and BAS calculations are separate steps. No Xero upload occurs.

## Shared runtime

Use the host Python 3.11+ runtime; packages installed by the setup check are found automatically. Source files are copied into the workspace documents directory and hash verified. Relative evidence paths survive moving the complete workspace. The canonical runtime is maintained once in `accounting_core/` and bundled automatically for standalone plugins.

## Show the review table in Codex

Create an invoice-review CSV from the returned invoice records when no review CSV exists. Include invoice ID, supplier, invoice number/date, currency, total_cents, gst_cents, review status, issues and source path. Open it before requesting extraction corrections or proceeding to matching.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/reports/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Pass the period so invoice rows get a **Not for this BAS** button (the user's way to leave out private, duplicate or zero-amount documents; it is saved straight to the books and can be put back). Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review" --start <period start> --end <period end>` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Sales and RCTIs

Import both supplier bills and customer sales/RCTIs with explicit `role: purchase` or `role: sale`; purchase remains the backward-compatible default. For sale records, contact_name is the customer/counterparty, not this business's supplier. RCTIs document the supplier's sale even when issued by the customer. Verify whose sale it is. Include the role in review CSVs. Credit notes retain positive amounts and the same purchase/sale role. Do not combine purchase and sales totals into one meaningful expense number.

## Settle these yourself

Do not leave these for the user. Record what you decided and why.

- **Australian supplier, no currency printed.** If the document shows an ABN, or an Australian address or phone number with `$` amounts, the currency is AUD. Put the ABN in `tax_invoice.supplier_abn` (the store then records AUD itself) and do not add a currency issue.
- **Not an invoice.** "Your invoice is ready" notifications, "payment received" or payment confirmations, and booking or itinerary emails carry no invoice of their own. Do not import them as invoices. Record each as supporting evidence: `accounting_store.py record-supporting --request <json>` with `{"business_id", "file", "kind": "notification" | "payment_confirmation" | "booking" | "other", "reason", "linked_invoice_id"}`. Link it to the real invoice when one is in the workspace (same supplier, amount or date). If the real invoice is missing, record it anyway and list it in the report as "Download the invoice from <supplier>": that is a task only the user can do. If it was already imported as an invoice, withdraw that record with `correct-record` first.

**No GST shown stays with the user.** Overseas suppliers (ARN instead of an ABN, "VAT"), receipts that lump taxes and fees together, and any invoice without a GST amount keep `needs_review`. Give one plain issue: "No GST shown: confirm no GST credit, or get a tax invoice." The user decides.

## Confirmed workspace currency

If `<workspace>/currency-confirmation.json` records this business ID, currency and explicit user evidence, reuse that currency for documents with missing currency. Do not ask again or leave a currency-only review blocker. Preserve the confirmation provenance; an explicit conflicting currency on a document must be reviewed rather than overwritten. This workspace setting does not establish GST eligibility.

## Fixed HTML report contract

Use the bundled `review-table` renderer for every CSV review. Its fixed HTML
and controls live in `scripts/review_table.py` (canonical package source:
`accounting_core/review_table.py`). Do not generate a replacement HTML page,
invent a dashboard, rewrite CSS, or change layout between runs. Preserve the
renderer’s column order from the exported CSV, controls, labels, formatting,
source links and correction-request behaviour. Data, title, period, row counts,
issue messages and schema-required columns may change; presentation must not.
A different export schema may have different columns without a new design.

Always save a standalone HTML invoice review alongside the dated CSV under
`<workspace>/output/YYYY-MM-DD/reports/`. The bundled review-table command
saves it before opening the live server and returns `saved_html`. Verify that
file exists and link it in the handoff, even when there are unresolved items.
Regenerate it after corrections. The saved copy must open offline with its
review rows and local document links. Keep previous snapshots.

For invoice reviews, populate a `review_action` field with one brief, plain-language
action per flagged row (aim for 3–10 words). Name the evidence or decision needed.
Consolidate repeated issues. Keep full reasons in `issues` for the expandable
follow-up. The renderer shows “No action needed” on clear rows.

Open and verify the returned browser URL. Keep detailed results in that report;
chat should provide its link and any necessary action/blocker, not a duplicate
table. If the renderer fails, report the failure and link the saved CSV as an
explicit fallback; do not improvise another HTML design. Template changes require
an explicit implementation request and belong in the canonical source, followed
by release generation to synchronise bundled copies, never in per-run output.

## Payment and claim handoff

Use match-payments to record confirmed payment ownership, claim approval and reimbursements through record-purchase. Extraction owns invoice facts only. Display saved claim fields returned by invoices without recreating or approving claims.

## Showing transactions

Whenever you show the user bank transactions (any list: "show me these", a payee group, the unclassified ones), run `export-transactions --start --end` with `--ids 12,15,...` for just those transactions (omit `--ids` for the whole period). It writes an Excel workbook in `output/` with a Summary by payee and one row per transaction showing its status (Classified, Proposed, Not classified), category and GST. Give the user the workbook link, plus a short grouped summary in chat (count and total per payee group). Never paste a table of more than 10 transactions in chat. For proposals the user will approve in Excel, use `export-proposals` instead: its Decision column can be applied back.

## Always end with the next step

Never finish a reply by saying work "remains open" or "is not ready" without saying what it is and what happens next. After any change, correction or answer:

1. Every command that changes the books returns `next_step.end_your_reply_with`: copy it word for word as the end of your reply. If a command returned none, run `workflow-status --start --end` for the period and write the same ending yourself.
2. In the reply itself (not only in a linked file), list each open step on its own line, lowest first, saying what is open and where it gets fixed, for example: "Step 4 Transactions: 12 payments still need a category (I'll show them grouped by payee)." or "Step 6 Reconciliation: the September closing balance doesn't match the statement by $40."
3. End with one question that starts the first item: "Shall I start Step 4: Transactions now?" If the user has said to keep going, start it instead of asking.

Never end a reply with a promise such as "I'll continue with…", "Next I'll…" or "I'll now…". The user sees that as work in progress, but your turn has ended and nothing happens. Either do that work now, in the same reply, and report it when done, or stop and ask the question in step 3. Only stop when you need the user's answer or the period has nothing open.

Never call anything pending, blocked, under review or unresolved without saying in the same sentence what resolves it and who does it, for example: "$2.73 OpenAI GST is pending: check the invoice; an ARN means no credit, an ABN means claim it." When posting GST as pending, `gst.resolve` must say exactly that; the command refuses pending GST without it.

If nothing is open, say so and offer the next stage. Use the step names from the BAS walkthrough (1 Setup, 2 Bank statements, 3 Invoices, 4 Transactions, 5 Payroll and BAS items, 6 Reconciliation, 7 BAS draft).

## Passing input to commands

Commands that take `--request`, `--records`, `--rule`, `--confirmed` or `--approved` read JSON from stdin when given `-`. Pipe the JSON in (`... --request - <<'JSON'` … `JSON`) instead of writing request files: every file you write is shown to the user as an edited file. Send several documents in one call where a command accepts a list, for example `record-supporting` with `{"documents": [...]}`.
