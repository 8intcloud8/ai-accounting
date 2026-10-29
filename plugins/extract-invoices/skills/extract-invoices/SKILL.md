---
name: extract-invoices
description: Extract locally saved bills, invoices and receipts into the assistant's persistent local accounting storage, with source links, GST, line items and review status. Use when the user asks to import or extract bills/invoices for accounting or BAS.
---

# Extract bills and invoices

## Official guidance for tax and regulatory decisions

Read `references/official-sources.md` when this task requires tax or regulatory interpretation. Use live official guidance, cite exact sources and access dates, and report access failures explicitly. Routine extraction/matching does not establish GST or deduction eligibility.

SQLite is internal assistant memory. Users provide documents, not database setup. This skill uses the same automatically managed `the selected workspace’s `db/accounting.db` (legacy fallback: `~/.ai-accounting/accounting.db`)` as bank imports; respect the `AI_ACCOUNTING_DB` override consistently.

## Workflow

1. Ask which folder contains bills/invoices, unless supplied. For a requested individual document use that file alone. Ask which business these documents belong to if not already known; reuse a stable business identifier. Do not scan unrelated folders.
2. Use saved local documents from Save Invoices when available. Search Bills returns candidates, not downloaded invoices. Save Invoices stores files and a manifest; neither proves invoice contents. Extract only after reading the actual file. Preserve originals.
3. Read PDFs using text extraction (pdfplumber) and images using visual inspection. Read CSV invoice records directly; give each record a stable `source_record` such as its invoice identifier or source row number. For scanned PDFs, report unavailable OCR rather than guessing. Invoice dates are ISO `YYYY-MM-DD`.
4. Extract supplier (not bill-to recipient), invoice number, invoice/due dates, total payable including tax, currency, GST explicitly printed on the invoice, and any available line items. Unknown fields stay null. Do not infer currency from `$` alone, or calculate GST as one-eleventh without source evidence. Treat receipts and credit notes explicitly; credit notes store positive amounts with `kind: credit_note`.
5. Show fields and uncertainties in chat. Use `review_status: verified` only after checking the required fields against the source and resolving issues. Otherwise use `needs_review` with an issue list. Missing GST remains unknown, never zero. If line items are complete and GST-inclusive, set `lines_complete: true`; include discounts as an issue instead of fabricating a positive line. Partial lines must not be labelled complete.
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
  "email_account": null,
  "email_message_id": null
}
```

For a document with one invoice use `source_record: single`. Include email identity only from actual Save Invoices metadata; never invent it.

7. Run the bundled storage helper (resolve this path relative to this skill directory):

```sh
python3 scripts/accounting_store.py import-invoices --records "<JSON path>"
python3 scripts/accounting_store.py invoices --business "<business ID>"
```

The helper creates or migrates storage automatically, validates amounts, preserves NULL values, records document hashes and local paths, and writes a batch atomically. An identical import is skipped. Changed extraction for the same source is rejected pending correction; possible supplier/invoice-number duplicates in different documents block for review. Do not alter identifiers to bypass conflicts. Use `correct-record` with kind invoice, id and a reason to withdraw an extraction, then reimport corrected data from the same source. Reverse dependent journals, allocations and matches first. History is retained.

8. Print a chat summary: documents processed, invoices added, existing invoices, needs-review count, verified totals per currency, and issues. Never combine currencies. Credit notes subtract from invoice totals. Invoice totals are amounts billed, not proof of payment or deductible expenditure. Use source paths for document links. Do not make users inspect raw JSON or manage the database.

## Scope

Stores invoice details and source references; original files must remain available. Payment matching, tax classifications, GST eligibility, and BAS calculations are separate steps. No Xero upload occurs.

## Shared runtime

Use the Python executable at `<suite>/.venv/bin/python` when installed, otherwise the host Python 3.11+ runtime. Source files are copied into the workspace documents directory and hash verified. Relative evidence paths survive moving the complete workspace. The canonical runtime is maintained once in `accounting_core/` and bundled automatically for standalone plugins.

## Show the review table in Codex

Create an invoice-review CSV from the returned invoice records when no review CSV exists. Include invoice ID, supplier, invoice number/date, currency, total_cents, gst_cents, review status, issues and source path. Open it before requesting extraction corrections or proceeding to matching.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review"` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Sales and RCTIs

Import both supplier bills and customer sales/RCTIs with explicit `role: purchase` or `role: sale`; purchase remains the backward-compatible default. For sale records, contact_name is the customer/counterparty, not this business's supplier. RCTIs document the supplier's sale even when issued by the customer. Verify whose sale it is. Include the role in review CSVs. Credit notes retain positive amounts and the same purchase/sale role. Do not combine purchase and sales totals into one meaningful expense number.

## Confirmed workspace currency

If `<workspace>/currency-confirmation.json` records this business ID, currency and explicit user evidence, reuse that currency for documents with missing currency. Do not ask again or leave a currency-only review blocker. Preserve the confirmation provenance; an explicit conflicting currency on a document must be reviewed rather than overwritten. This workspace setting does not establish GST eligibility.
