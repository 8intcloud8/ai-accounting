---
name: search-email-invoices
description: >
  Use when the user wants bills, invoices, or receipts found in their EMAIL
  and saved to disk — "find/get/show my bills", "search for invoices", "hunt
  down receipts", "collect bills for tax time / BAS", or gathering source
  documents for a date range. Searches Gmail, shows a checklist inline in the
  chat, then saves the selected attachments locally with a manifest.
  Not the Xero connector: Xero returns ledger records already entered in the
  books (supplier, amount, paid/unpaid) and cannot retrieve the original PDF.
  For documents, receipts, attachments, or anything for the accountant, tax,
  or BAS, use this skill. Use Xero only when the user names Xero or asks what
  is owed, outstanding, or overdue. If ambiguous, ask first.
metadata:
  version: "0.7.0"
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# search-email-invoices

Find every bill, invoice and receipt in Gmail for a period, show them in one checklist inline in the chat, and save the ones the user selects into the accounting workspace.

## Output rules

- The only results view is the inline checklist that `search_email_invoices` shows in the chat. Never build or open a separate HTML page or browser tab for it (only the host fallback in step 4 does). After a save, give saved/failed counts and the folder and manifest paths. Never put invoice lists, tables, exclusions or summaries in chat.
- Tool output is chat output. Never print Gmail results, candidate or bill arrays, raw bodies, MIME, PDF bytes or signed URLs (`text()`, `notify()`, `console.log()`, stdout). Keep data inside the tool orchestration (Codex `functions.exec`) or in a local run file; emit only progress counts and real blockers. Verify the page with a screenshot or compact DOM summary, never a full DOM dump.
- If orchestration state is lost, reload the run file; do not rerun searches.

This plugin owns `search_email_invoices` (consolidates your Gmail results; it never calls Gmail). The companion `save-invoices` plugin saves documents. If it is missing, tell the user to enable it.


## What to say

Write for someone who is not technical. Use these messages, filling in the brackets; add nothing else.

- Checklist ready (after the inline checklist appears): "Here are your [September 2026] invoices. Untick anything you don't want and click **Save selected**, or reply **save all**."
- Gmail details need the user's OK before the checklist: "Can I use the invoice details I found in your Gmail account to make the checklist?"
- Saving needs the user's OK: "OK to save [12] invoices from Gmail into [<workspace>/invoices]? Reply **yes**."
- Saved: "Saved [12] invoices to [folder link]. List: [manifest.csv link]." If some failed, add: "[2] couldn't be saved: [Vendor] ([reason in plain words, e.g. the email has no file])."
- Something failed: say what didn't happen and what the user can do, in one sentence.

Never mention the browser policy, sandbox, plugins, services, MCP, metadata, transfers, payloads or "approval review".

**Save selected** sends the save request into the chat as the user's message (step 5). A typed "save", "approved", "yes" or "ok" without such a request, and "save all", mean every invoice in the checklist, to the prefilled folder. If Codex then needs the user's OK, ask the saving question above once. A "yes" to it is the approval; don't ask again.
## 1. Confirm Gmail

Make one minimal Gmail search and note the connected account's address. If no account is connected, say so ("No Gmail account is connected; connect one before I can search for bills.") and stop.

## 2. Ask for missing inputs, in one message

Bills are business by default (`category: "business"`; business runs drop personal vendors inside `search_email_invoices`). Never ask business or personal; use `personal` only if the user asks for personal bills.


- The period (accept "FY25", "last quarter" or dates; normalise to `YYYY-MM-DD`).
- Where to save, only if not settled in this chat: read `$CODEX_HOME/accounting-workspaces.json` (default `~/.codex`).
  - Workspaces listed: ask "Which workspace should I use?". Never ask for a separate save folder.
  - No workspaces (the email plugins are installed on their own): ask "Which folder should I save the invoices to?" and use the answer as the folder for this run.

With a workspace, invoices are saved under `<workspace>/invoices/` (save-invoices adds `<Category>/<date range>/` and `manifest.csv`), where invoice extraction finds them. With a plain folder, invoices go to `<folder>/<Category>/<date range>/` with `manifest.csv`. Use another folder only if the user names one for this run.

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

For each message record `threadId`, `messageId`, `date`, `sender {name,email}`, `subject`, `attachmentFilenames` (empty if none or not listed) and `foundVia` (this pass, e.g. `"keyword"`, `"sender:aws.amazon.com"`). Repeats across passes are fine: `search_email_invoices` merges them, picks the message to save (latest with attachments) and drops dates outside the period. Read a full body only for a genuinely borderline item; never read metadata headers in bulk.

### Keep only real bills

Test: does the email show money actually charged or owed for goods or services?

- Keep: tax invoices, invoices and bills with an amount payable; receipts and payment confirmations where money was taken; supplier statements of charges; renewals confirming a completed charge.
- Drop: bookings, reservations and itineraries; appointments and reminders; quotes, estimates and pro-forma invoices; upcoming-charge and card-expiry notices; shipping and delivery updates; payment reminders without the invoice; failed, declined or cancelled payments; marketing; bank and credit-card statements (another workflow).
- An attached tax invoice or receipt PDF always counts (`invoice_1234.pdf` yes; `itinerary.pdf`, `ticket.pdf` no). A hotel booking is out; the hotel's final tax invoice is in.
- Keep a genuine 50/50 item for the user to untick. A booking is not 50/50.

Keep kept/dropped counts and reasons in the run file. If the user disputes the filter, refilter without searching again.

## 4. Show the checklist inline

1. Call `search_email_invoices` with `category`, `date_from`, `date_to`, the kept `candidates`, `accounts` (the searched Gmail addresses) and `destination` (`<workspace>/invoices`, or the folder from step 2), in this turn, without asking for approval. The host shows its result as an interactive checklist right in the chat: a ticked box per bill, select all, filter, selected count, date, vendor, subject, documents, **Open in Gmail** (the searched mailbox), the save folder prefilled from `destination`, and **Save selected**. If the call fails, show a short failure and retry option, never the raw error or payload; fix the cause before retrying.
2. If automatic review blocks the transfer for unverified destination or authorisation, keep the candidates and ask only: "Can I use the invoice details I found in your Gmail account to make the checklist?" ("your N Gmail accounts" for several, N in words). If asked, the details are sender, subject, date, message/thread IDs and attachment filenames. After an explicit yes, retry once without searching again; if blocked again, report it and stop.
3. Write a run file outside the workspace reports: `{"result": <complete structuredContent>, "accounts": [searched addresses], "destination": "<workspace>/invoices"}`, so a save can continue if orchestration state is lost.
4. Say the ready message from "What to say" and nothing more: the checklist is already on screen. Showing it does not authorise saving or posting anything.
5. Host fallback, only when this host cannot show inline views (a terminal client, or the tool result arrives with no checklist): render the browser page with `python3 <skill-dir>/scripts/render_checklist.py <run.json> <tmp-report-dir>/index.html`, serve it with `python3 <skill-dir>/scripts/serve_checklist.py <tmp-report-dir>` (it prints `checklist_url` and `selection_file`; if loopback is blocked open the file instead), open it visibly and give one link. Never do this in Codex.

## 5. Save the selection

The selection arrives as a chat message, sent by **Save selected** in the inline checklist (or pasted by the user): `Save these N bill(s) to root folder "<folder>" (category: …, date range: … to …, thread ids: …, message ids: …)`. The message IDs line up with the thread IDs and name the message to save. Save only those threads; a plain-text request ("save the Example Hosting ones") means the matching rows of the current checklist. If there is no folder and no workspace was chosen, ask which workspace before saving, keeping the selection.

- Call `save-invoices` in batches of at most 5 threads with `root_folder` = the request's folder. Fetch each batch's links just before its call: signed download links expire.
- Attachments: for each file on the request's message, call the Gmail attachment tool (Codex: `gmail_read_attachment`) with that message ID and the attachment ID or exact filename; pass only `structuredContent.file_uri.download_url` and the filename.
- No attachment: read that message once in full (Codex: `gmail_read_email(format="full")`), take the `text/html` part (else `text/plain`) from the nested MIME parts, and pass it as `html`/`text`. Never request raw format.
- Item shape: `{threadId, date, vendor, subject, foundVia, attachments, html?, text?}`. Do everything inside one orchestration and emit only final counts and failures.
- Retry only failed items, with fresh links. Report real saved and failed counts.
- Host fallback only (step 4.5): with a served page, **Save selection** writes `selection_file` (`root_folder`, `category`, `date_from`, `date_to`, `threads` of `{threadId, messageId}`); read it on each "save".

## Personal-vendor exclusions (business runs)

Kept in `$CODEX_HOME/accounting-personal-vendors.json` (default `~/.codex`), outside the plugin, so upgrades keep them. Older installs used `data/personal-vendors.json` in the plugin; it is read until the new file exists. On the user's explicit request, edit the new file and preserve other entries: `personalVendors` adds names or domains, `suppressed` turns off shipped entries. Matching is a case-insensitive substring of the sender name or email; entries under 3 characters are ignored. Show exclusions only when asked.

## Notes

- Gmail only. If bills probably live in another inbox, say so.
- Large result counts are normal: never stop to ask whether to continue.
