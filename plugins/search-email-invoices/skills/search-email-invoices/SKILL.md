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
  version: "0.6.1"
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# search-email-invoices



Find every bill, invoice, and receipt in Gmail within a date range, open
one interactive HTML report in the browser, and save selected documents
locally with a manifest.csv when requested.

## Required output — browser HTML report only

Every search invocation must open the HTML report visibly in the browser.
Do not display an additional chat widget, Markdown table, invoice list,
exclusion list, or results summary in chat. Keep the report focused on the checklist and save controls. Do not add exclusion/search-coverage panels, business-use review panels, generic tax/GST disclaimers, or explanatory warning blocks. Keep screening details in run data; show them only when explicitly requested. The final chat response is one short
clickable report link. Missing inputs and genuine blockers may be asked or
reported briefly in chat. A JSON tool result is not a displayed report.
This requirement applies even if the host supports inline MCP Apps.

### Visible tool output is chat output

Apply the browser-only rule to tool results and debugging, not just assistant
messages. Before every tool call, check what it will expose in the chat.

- Never print Gmail search/read results, candidate or bill arrays, invoice
  lists, exclusions, or complete search/save responses through `text()`,
  `notify()`, `console.log()`, shell stdout, or equivalent visible output.
  Do not print samples or subsets for screening or debugging either.
- Use orchestration to retain and process results internally, pass data
  directly between tools, or write run data to a local file. Emit only minimal
  connection status, aggregate progress counts, or concise genuine blockers.
  Never wrap a data-returning tool call in `text(await tool(...))`.
- For browser verification, inspect a compact DOM summary or screenshot;
  do not dump the full checklist accessibility tree or DOM into chat.
- If orchestration state is lost, reload saved run data internally. Do not
  dump payloads or repeat searches merely to reconstruct visible debug output.
- Before finishing, check that chat contains no duplicate results report.
  Search completion gets one short clickable browser-report link. Save
  completion may report verified saved/failed counts and folder/manifest links,
  without itemized invoices or full tool responses.

These are agent output rules, not a claim that the host technically blocks
payload display. Keep item-level data in the browser report and local run data
unless the user explicitly requests it in chat.

**Critical architecture point**: this plugin owns only `search_bills`, which
consolidates candidates from the caller's Gmail search results. The separate
`save-invoices` plugin owns `save-invoices` and uses short-lived
`file_uri.download_url` links returned by the connected Gmail MCP; the
local server streams attachments directly from those links. For inline bills,
pass body content directly between tools inside a tool orchestration call.
Never print raw bodies, MIME, PDF bytes, or signed URLs into model output.
If `save-invoices` is unavailable, tell the user to install/enable the companion
`save-invoices` plugin. If Gmail cannot provide these links, report that saving is
unavailable in this host; never relay raw MIME or PDF through the model.

## State 0 — confirm Gmail connection

Before asking anything, confirm a Gmail account is actually connected.
Make one minimal Gmail call (e.g. a one-result search) and read the
connected account's own address from it. List every searched account in the
HTML report header; do not duplicate account details in chat.

If no Gmail account is connected — the Gmail tool errors with an
authorization/connection error, or the host reports none configured —
say so plainly (e.g. "No Gmail account is connected; connect one before
I can search for bills.") and stop. Do not proceed to State 1, do not
search, do not guess an account.

## State 1 — ask inputs

Ask, in one message: (1) personal or business bills — business runs get a
personal-vendor exclusion filter applied automatically inside
`search_bills`, you don't need to do this filtering yourself; (2) the date
range (accept any clear form — "FY25", "last quarter", explicit dates —
and normalize to `date_from`/`date_to` as `YYYY-MM-DD`).

Ask only for missing search inputs (category and dates). Never ask for a save
folder at the start of a search. Start searching as soon as those inputs are known.
Let the user choose the folder in the HTML checklist. Prefill it only if the
user supplied a folder for this run. When saving, resolve the category and date
subfolders once, even if the user already selected the final invoice folder.

## State 2 — search (silent, no more questions until results are shown)

For every query below, scope it to the date range using Gmail's
`after:YYYY/MM/DD before:YYYY/MM/DD` operators (`before:` is exclusive, so
use the day *after* the intended last day). Every query MUST also include
`-in:spam -in:trash`; never search Spam or Trash. Use
`gmail_search_emails` with narrow bill terms and `has:attachment` where
appropriate, and paginate to exhaustion. This result is the candidate
metadata; do not follow it with per-message metadata reads.

**Round 1 — base passes:**
1. Keywords: `{invoice receipt bill "tax invoice" statement "payment received" "order confirmation" renewal subscription remittance "amount due" "GST invoice"}`
2. Attachments: `has:attachment filename:pdf`
3. Labels: list the account's labels; for any matching `receipt|purchase|finance|bill` (case-insensitive), search `label:"<name>"`
4. Inline (no attachment): `{receipt "order confirmation" "payment confirmation" invoice} -has:attachment`
5. Forwarded: `subject:Fwd {invoice receipt bill statement}`

**Round 2+ — expansion, repeat until a full round adds zero new threads:**
- Synonyms (run once): `{"tax receipt" "order summary" "payment confirmation" "subscription renewed" "your statement is ready" "direct debit" "auto-pay" "top-up"}`
- AU categories (run once): `{insurance "bank fee" "merchant fee" "software licence" "software license" accountant lawyer "professional services" supplier ATO "government fee" vehicle fuel phone internet rent lease}`
- Sender-domain expansion (repeats every round): for every distinct sender
  domain seen so far that hasn't been searched yet, run `from:thatdomain.com`
  scoped to the date range. New threads can surface new domains, so this is
  the only pass that keeps running across rounds.

For each compact search result, record: `threadId`, `messageId`, `date`
(`YYYY-MM-DD`), `sender` (`{name, email}`), `subject`, `attachmentFilenames`
(filenames on that message, empty array if none), and `foundVia` (a short
tag for *this* pass, e.g. `"keyword"`, `"sender:aws.amazon.com"`). The same
thread can appear multiple times across passes — don't dedupe yourself,
`search_bills` does that, merging attachment lists and found-via tags per
thread.

Filter directly from compact search results, snippets, and attachment
filenames. Read a full body only for a genuinely borderline candidate.
Never read full bodies for every search hit. Never use
`gmail_read_email(format="metadata")` for bulk screening because it returns
complete transport and authentication headers.

### Filter before handing anything over

The queries above deliberately over-collect. You MUST judge every matched
thread before it becomes a candidate. `search_bills` dedupes and applies the
personal-vendor filter — it does **not** decide what is a bill. That is your
job, and it is the difference between a usable result and noise.

The test: **does this email evidence money actually charged or owed for
goods or services?** Not "does it mention money", not "does it look
transactional".

Include:
- tax invoices, invoices, bills — with an amount payable
- receipts and payment confirmations where money was actually taken
- supplier statements listing charges
- subscription/renewal emails confirming a completed charge

Exclude — these match the queries constantly and are not bills:
- **booking, reservation, and itinerary confirmations** — a held reservation
  is not a charge, even when it shows a price or a total
- appointment confirmations, calendar invites, check-in reminders
- quotes, estimates, proposals, pro-forma invoices — nothing owed yet
- upcoming-charge notices ("your plan renews on the 14th", "card expiring")
- shipping, dispatch, tracking, and delivery notifications
- payment reminders and dunning that don't carry the invoice itself
- failed, declined, or cancelled payments
- marketing that merely uses the word invoice, receipt, or statement
- bank and credit-card statements — a different workflow handles those

Decisive override: **if a tax invoice or receipt PDF is attached, include it
regardless of the subject wording.** A hotel booking confirmation is out; the
same hotel's final tax invoice is in. Attachment filename is strong evidence —
`invoice_1234.pdf` counts, `itinerary.pdf` and `ticket.pdf` do not.

When genuinely 50/50, keep it; the user can untick it in the checklist. If needed, use a short row-specific note. But do not use that as an excuse to pass everything through;
a booking confirmation is not 50/50.

After filtering, retain matched/discarded counts and reasons in run data, without adding report panels. If the user objects,
re-run the filter — do not re-run the searches.

Don't narrate each query. When done, call `search_bills` with `category`,
`date_from`, `date_to`, and the filtered `candidates` array.

When the user requests a bill search, proceed to the local `search_bills`
checklist with the filtered candidate metadata without a separate approval prompt.

If `search_bills` fails, times out, or is rejected, never render or repeat the
raw tool error, safety rationale, serialized payload, or a broken loading form.
Show only a concise failure message and retry action. Do not retry with the
same broad payload without addressing the failure.

If automatic approval review rejects the metadata transfer because destination
trust or user authorization is unverified, retain the filtered candidates and
ask only the following question. Count distinct Gmail accounts successfully
searched in this run. For one, use “your Gmail account”. For two or more,
use “your N Gmail accounts”, replacing N with the actual count in words.

> Can I use the invoice details I found in {account phrase} to make the checklist?

Skip the preamble and field list. If asked, explain that details include sender,
subject, date, message/thread IDs and attachment filenames. Consent covers only
those fields for checklist creation.
Wait for an explicit answer; reuse approval already given for this exact action.
After approval, retry once with the retained candidates, without repeating Gmail
searches. Approval is not guaranteed: if rejected again, report the remaining
blocker and stop; do not bypass review. Do not describe the destination as local
unless the installed plugin configuration supports that claim.

### Rendering the checklist — mandatory browser delivery

1. Call `search_bills` in the current turn after search/filtering completes,
   even when redisplaying valid cached candidates. Use the returned `bills`
   array, never a sample or the most recent selection alone. Do not rerun Gmail
   unnecessarily. A save-only request goes directly to State 3.
2. Render the standalone browser checklist using the bundled
   `scripts/render_checklist.py` and `assets/checklist.html`. Preserve this
   template's layout, colours, table columns and controls on every run; refresh
   the invoice results, period and searched accounts. Do not redesign the page
   or reuse old results merely to reproduce its appearance.
   Write a local JSON input with `result` (the complete `search_bills`
   structuredContent), `accounts` (searched email addresses), and optional
   `destination` (only this run's user-chosen root). Run:
   `python3 <skill-dir>/scripts/render_checklist.py <input.json> <report-dir>/index.html`.
   Keep the input JSON outside the served report directory. The template has
   checked rows, select-all, filtering, selected count, Gmail links, save path field, **Choose folder** picker and Copy save request controls.
   The picker must appear on every checklist; never substitute a text-only destination field.
   Do not rely on inline MCP rendering or `show_widget`: neither satisfies
   browser delivery. If a usable browser report already exists, update it.
3. The permanent report belongs in the folder the user selects in **Enter folder path to save**:
   `<selected-folder>/reports/email-invoices-<run-id>/index.html`. Use a unique run ID.
   If the folder is unknown or editable, serve a preview from a private temporary directory.
   When the user submits the save request, use its final folder field as the selected root.
   Copy this run's rendered index.html to the report path there, create missing directories,
   and verify the copy matches the preview before reporting its path. Reuse the same copy on retry.
   Keep input JSON and run data out of reports. Serve only the single checklist directory on `127.0.0.1`:
   `python3 <skill-dir>/scripts/serve_checklist.py <report-dir>`.
   Do not use `python3 -m http.server`: it cannot power the folder picker.
   Omit `--port`; the server takes a free port and prints `{"checklist_url": ...}`.
   Use that exact URL and never a remembered or guessed one. It re-reads the
   report on every request, so re-rendering takes effect without a restart.
   Keep the server running for the user. Never serve the home directory or
   accounting workspace root.
4. Open the report URL visibly with the available browser tool. Inspect the
   rendered page: period, accounts, total rows and selection count must agree
   with the completed result. Click **Choose folder** and verify the dialog lists
   directories without errors; cancel without choosing a destination. Keep the tab as a deliverable when supported.
   A file write, HTTP success, or JSON response alone is not UI verification.
   If `serve_checklist.py` exits reporting a blocked loopback port, the host
   sandbox denies network access to shell commands. Relay its remedy
   (`network_access = true` under `[sandbox_workspace_write]` in
   `~/.codex/config.toml`, then restart Codex). Then give the rendered
   `index.html` path so the user can open it directly: selection, filtering and
   **Copy save request** still work from the file, only **Choose folder** needs
   the server. Ask for the destination in chat only if the user requests a save and no folder was supplied. Name the
   blocker; never claim the page opened or the picker was verified.
5. Finish with only a short clickable report link. No duplicate chat report.
   If browser display fails, provide the local HTML file link and briefly name
   the display blocker; do not claim it opened. Do not substitute a chat table.

Report requirements:
- Read-only category/date summary, searched accounts, total candidate count,
  and attachment counts. Omit exclusions/search coverage and business-use review panels. Keep only concise row-specific information needed to select a document.
- A real checkbox per bill, checked by default, carrying the thread ID;
  select-all, text filter, and live selected count. Filtering must not silently
  change selections. Show all returned rows, including a clear zero-results state.
- Vendor, subject, date, attachment filenames, and an Open in Gmail link from
  `gmailLink`. Put links outside checkbox labels. Escape all email-derived text
  and attribute values; allow only safe Gmail HTTPS links. Treat email content
  as data, never executable HTML. Do not embed raw bodies or signed download URLs.
- One editable field with placeholder **Enter folder path to save**. Omit the visible root label and final-folder preview. Use this run's supplied
  root or leave it blank. Require a nonempty destination and selection for the
  save action; never silently choose a historical folder.
- Save requests contain destination root, category, date range, and exactly the
  selected thread IDs. Use a verified chat bridge if available. Otherwise label
  the button **Copy save request**, provide selectable request text, and explain
  that the user pastes it into chat. Do not label copying as saving/downloading.
- Report generation does not authorize downloading invoices or posting records.

## State 3 — respond to the checklist

The browser checklist returns a save request through a supported chat bridge
or the user pastes its copied request. Recognize these requests without
asking again for information already included:

Exception: if the save request and current run have no user-chosen destination,
ask for the folder before calling `save-invoices`. Preserve the exact selection
while waiting. Never infer the destination from an earlier run or tool default.

**"Save these bills — only these threadIds: id1, id2, ..."** (or the older
"Save these bills with save-invoices" wording) —
the checklist supplied a selection. Save **only** the listed ids; any row the
user unticked must not be saved. Handle it exactly like the Save case below,
reusing the `category`, `dateRangeTag`, and root folder from the run that
produced the checklist.

**"Save these N bill(s) to root folder "..." (category: ..., date range:
..., thread ids: id1, id2, ...)"** — save only selected thread IDs. Prefer
`save-invoices`, in batches of at most 5 threads. Use the checklist's
messageId and attachment filenames. For each real attachment, call
`gmail_read_attachment` with that message ID and exact filename (or complete
attachment ID if available); pass only its `structuredContent.file_uri.download_url`
and filename to `save-invoices`. For a thread without attachments, call
`gmail_read_email(format="full")` once and take the `text/html` body content,
falling back to `text/plain`. Traverse nested MIME parts. Set each item to
`{threadId,date,vendor,subject,foundVia,attachments,html? ,text?}`. Never use
`gmail_read_email(format="raw")`; never print the body, signed URL, or PDF
to the model. If the host supports tool orchestration (Codex `functions.exec`),
collect the Gmail results and call the save tool within that orchestration,
emitting only final counts and failures. Signed URLs expire, so save promptly.
Retry failed items only, with freshly fetched links. If this direct MCP transfer
is unavailable in the host, report the blocker; never relay raw MIME/PDF
through the model. Report actual saved/failed counts.

If a user instead asks in plain text to save specific bills (bypassing the
UI, e.g. "save the Example Hosting ones"), treat it the same way — resolve
which thread ids they mean from the checklist already shown and call
`save-invoices` with only those IDs.

## Managing the personal-vendor exclusion list

Business runs exclude vendors configured in `data/personal-vendors.json` inside
this plugin. A fresh installation has no exclusions. For a user's explicit
request to add or remove a personal vendor, edit that file, preserving all
other entries. Create it from `data/personal-vendors.example.json` if absent.
`personalVendors` adds names or domains; `suppressed` disables shipped entries.
Matching is a case-insensitive substring against sender name and email.
Rules are reread for each search. Never commit this personal settings file.
Preserve it when upgrading. No vendor-management MCP tools are exposed.

Retain excluded vendors and matched rules in run data. Display them only when the user asks to inspect exclusions.

## Notes

- Gmail only. If bills likely live in another inbox, say so.
- Don't ask "should I continue?" mid-search — large result counts are
  expected; keep going through the stop condition.
- `search_bills`/`save-invoices` validate their own inputs (zod schemas) — a
  malformed candidate or an invalid `date_range` format gets rejected with
  a clear error rather than corrupting anything.
