---
name: search-email-invoices
description: >
  Use when the user wants bills, invoices, or receipts found in their EMAIL
  and saved to disk — "find/get/show my bills", "search for invoices", "hunt
  down receipts", "collect bills for tax time / BAS", or gathering source
  documents for a date range. Searches Gmail, opens a browser HTML checklist, then
  saves the selected attachments locally with a manifest.
  Not the Xero connector: Xero returns ledger records already entered in the
  books (supplier, amount, paid/unpaid) and cannot retrieve the original PDF.
  For documents, receipts, attachments, or anything for the accountant, tax,
  or BAS, use this skill. Use Xero only when the user names Xero or asks what
  is owed, outstanding, or overdue. If ambiguous, ask first.
metadata:
  version: "0.6.9"
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# search-email-invoices

Find every bill, invoice and receipt in Gmail for a period, show them in one browser checklist, and save the ones the user selects into the accounting workspace.

## Output rules

- The only results view is the browser checklist. In chat, give one short clickable link to it; after a save, give saved/failed counts and the folder and manifest paths. Never put invoice lists, tables, exclusions or summaries in chat, and add no panels, disclaimers or warnings to the page.
- Tool output is chat output. Never print Gmail results, candidate or bill arrays, raw bodies, MIME, PDF bytes or signed URLs (`text()`, `notify()`, `console.log()`, stdout). Keep data inside the tool orchestration (Codex `functions.exec`) or in a local run file; emit only progress counts and real blockers. Verify the page with a screenshot or compact DOM summary, never a full DOM dump.
- If orchestration state is lost, reload the run file; do not rerun searches.

This plugin owns `search_bills` (consolidates your Gmail results; it never calls Gmail). The companion `save-invoices` plugin saves documents. If it is missing, tell the user to enable it.

## 1. Confirm Gmail

Make one minimal Gmail search and note the connected account's address. If no account is connected, say so ("No Gmail account is connected; connect one before I can search for bills.") and stop.

## 2. Ask for missing inputs, in one message

- Personal or business bills (business runs drop personal vendors inside `search_bills`).
- The period (accept "FY25", "last quarter" or dates; normalise to `YYYY-MM-DD`).
- The workspace, only if none was chosen in this chat: read `$CODEX_HOME/accounting-workspaces.json` (default `~/.codex`) and ask "Which workspace should I use?". Never ask for a separate save folder.

Invoices are saved under `<workspace>/invoices/` (save-invoices adds `<Category>/<date range>/` and `manifest.csv`), where invoice extraction finds them. The checklist report is kept at `<workspace>/output/<YYYY-MM-DD>/reports/email-invoices-<run-id>/index.html`. Use another folder only if the user names one for this run.

## 3. Search (no questions, no narration)

Every query: `after:YYYY/MM/DD before:YYYY/MM/DD` (`before:` is the day after the last day) and `-in:spam -in:trash`. Use the Gmail connector's search tool (Codex: `gmail_search_emails`) and page to the end. The search results are the candidate metadata; do not read messages one by one.

Round 1:
1. `{invoice receipt bill "tax invoice" statement "payment received" "order confirmation" renewal subscription remittance "amount due" "GST invoice"}`
2. `has:attachment filename:pdf`
3. For each label matching `receipt|purchase|finance|bill` (case-insensitive): `label:"<name>"`
4. `{receipt "order confirmation" "payment confirmation" invoice} -has:attachment`
5. `subject:Fwd {invoice receipt bill statement}`

Round 2 onward, once each: synonyms `{"tax receipt" "order summary" "payment confirmation" "subscription renewed" "your statement is ready" "direct debit" "auto-pay" "top-up"}`; Australian categories `{insurance "bank fee" "merchant fee" "software licence" "software license" accountant lawyer "professional services" supplier ATO "government fee" vehicle fuel phone internet rent lease}`.

Sender expansion, every round: `from:<domain>` for each sender domain kept as a bill (not every domain seen) and not yet searched. Skip personal mail providers: gmail.com, googlemail.com, outlook.com, hotmail.com, live.com, yahoo.com, icloud.com, me.com, bigpond.com, optusnet.com.au. Stop when a round adds no new bill, or after 3 expansion rounds.

For each message record `threadId`, `messageId`, `date`, `sender {name,email}`, `subject`, `attachmentFilenames` (empty if none or not listed) and `foundVia` (this pass, e.g. `"keyword"`, `"sender:aws.amazon.com"`). Repeats across passes are fine: `search_bills` merges them, picks the message to save (latest with attachments) and drops dates outside the period. Read a full body only for a genuinely borderline item; never read metadata headers in bulk.

### Keep only real bills

Test: does the email show money actually charged or owed for goods or services?

- Keep: tax invoices, invoices and bills with an amount payable; receipts and payment confirmations where money was taken; supplier statements of charges; renewals confirming a completed charge.
- Drop: bookings, reservations and itineraries; appointments and reminders; quotes, estimates and pro-forma invoices; upcoming-charge and card-expiry notices; shipping and delivery updates; payment reminders without the invoice; failed, declined or cancelled payments; marketing; bank and credit-card statements (another workflow).
- An attached tax invoice or receipt PDF always counts (`invoice_1234.pdf` yes; `itinerary.pdf`, `ticket.pdf` no). A hotel booking is out; the hotel's final tax invoice is in.
- Keep a genuine 50/50 item for the user to untick. A booking is not 50/50.

Keep kept/dropped counts and reasons in the run file. If the user disputes the filter, refilter without searching again.

## 4. Build and show the checklist

1. Call `search_bills` with `category`, `date_from`, `date_to` and the kept `candidates`, in this turn, without asking for approval. If it fails, show a short failure and retry option, never the raw error or payload; fix the cause before retrying.
2. If automatic review blocks the transfer for unverified destination or authorisation, keep the candidates and ask only: "Can I use the invoice details I found in your Gmail account to make the checklist?" ("your N Gmail accounts" for several, N in words). If asked, the details are sender, subject, date, message/thread IDs and attachment filenames. After an explicit yes, retry once without searching again; if blocked again, report it and stop.
3. Write a run file outside the report folder: `{"result": <complete structuredContent>, "accounts": [searched addresses], "destination": "<workspace>/invoices"}`. Render with `python3 <skill-dir>/scripts/render_checklist.py <run.json> <tmp-report-dir>/index.html`. Do not change the template's layout, colours, columns or controls.
4. Serve only that folder: `python3 <skill-dir>/scripts/serve_checklist.py <tmp-report-dir>` (no `--port`; never `python3 -m http.server`, it cannot run the folder picker). Use the exact `checklist_url` it prints. It rereads the page on every request, so re-rendering needs no restart. Never serve the home folder or the workspace root.
5. Open the URL visibly in the browser. Check that the period, accounts, row count and selected count match the result, and that **Choose folder** lists folders (then cancel). An HTTP 200 or file write is not a check.
6. If the server reports a blocked loopback port, relay its fix (`network_access = true` under `[sandbox_workspace_write]` in `~/.codex/config.toml`, then restart Codex) and give the `index.html` path: everything but **Choose folder** works from the file. Never claim the page opened.

The page (already built into the template): a checked box per bill, select-all, filter, selected count, vendor, subject, date, documents, an **Open in Gmail** link for the searched mailbox, a save field prefilled with `<workspace>/invoices`, **Choose folder**, and **Copy save request**. All email text is escaped and only Gmail HTTPS links are allowed. Showing the page does not authorise saving or posting anything.

## 5. Save the selection

The user pastes the copied request: `Save these N bill(s) to root folder "<folder>" (category: …, date range: … to …, thread ids: …, message ids: …)`. The message IDs line up with the thread IDs and name the message to save. Save only those threads; a plain-text request ("save the Example Hosting ones") means the matching rows of the current checklist. If there is no folder and no workspace was chosen, ask which workspace before saving, keeping the selection.

- Call `save-invoices` in batches of at most 5 threads with `root_folder` = the request's folder. Fetch each batch's links just before its call: signed download links expire.
- Attachments: for each file on the request's message, call the Gmail attachment tool (Codex: `gmail_read_attachment`) with that message ID and the attachment ID or exact filename; pass only `structuredContent.file_uri.download_url` and the filename.
- No attachment: read that message once in full (Codex: `gmail_read_email(format="full")`), take the `text/html` part (else `text/plain`) from the nested MIME parts, and pass it as `html`/`text`. Never request raw format.
- Item shape: `{threadId, date, vendor, subject, foundVia, attachments, html?, text?}`. Do everything inside one orchestration and emit only final counts and failures.
- Retry only failed items, with fresh links. Report real saved and failed counts.
- Copy this run's rendered page to `<workspace>/output/<YYYY-MM-DD>/reports/email-invoices-<run-id>/index.html` (outside a workspace: `<folder>/reports/…`), check it matches, and reuse that copy on retry.

## Personal-vendor exclusions (business runs)

Kept in `$CODEX_HOME/accounting-personal-vendors.json` (default `~/.codex`), outside the plugin, so upgrades keep them. Older installs used `data/personal-vendors.json` in the plugin; it is read until the new file exists. On the user's explicit request, edit the new file and preserve other entries: `personalVendors` adds names or domains, `suppressed` turns off shipped entries. Matching is a case-insensitive substring of the sender name or email; entries under 3 characters are ignored. Show exclusions only when asked.

## Notes

- Gmail only. If bills probably live in another inbox, say so.
- Large result counts are normal: never stop to ask whether to continue.
