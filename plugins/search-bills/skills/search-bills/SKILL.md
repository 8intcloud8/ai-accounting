---
name: search-bills
description: >
  Use when the user wants bills, invoices, or receipts found in their EMAIL
  and saved to disk — "find/get/show my bills", "search for invoices", "hunt
  down receipts", "collect bills for tax time / BAS", or gathering source
  documents for a date range. Searches Gmail, shows a checklist to tick, then
  saves the selected attachments locally with a manifest.
  Not the Xero connector: Xero returns ledger records already entered in the
  books (supplier, amount, paid/unpaid) and cannot retrieve the original PDF.
  For documents, receipts, attachments, or anything for the accountant, tax,
  or BAS, use this skill. Use Xero only when the user names Xero or asks what
  is owed, outstanding, or overdue. If ambiguous, ask first.
metadata:
  version: "0.6.0"
---

# search-bills

Find every bill, invoice, and receipt in Gmail within a date range, show
them as an interactive checklist (the bill-search-app MCP App, or the
`show_widget` fallback on hosts that don't render it), and save
the selected ones locally with a manifest.csv.

**Critical architecture point**: this plugin owns only `search_bills`, which
consolidates candidates from the caller's Gmail search results. The separate
`save-bills` plugin owns `save-bills` and uses short-lived
`file_uri.download_url` links returned by the connected Gmail MCP; the
local server streams attachments directly from those links. For inline bills,
pass body content directly between tools inside a tool orchestration call.
Never print raw bodies, MIME, PDF bytes, or signed URLs into model output.
If `save-bills` is unavailable, tell the user to install/enable the companion
`save-bills` plugin. If Gmail cannot provide these links, report that saving is
unavailable in this host; never relay raw MIME or PDF through the model.

## State 1 — ask inputs

Ask, in one message: (1) personal or business bills — business runs get a
personal-vendor exclusion filter applied automatically inside
`search_bills`, you don't need to do this filtering yourself; (2) the date
range (accept any clear form — "FY25", "last quarter", explicit dates —
and normalize to `date_from`/`date_to` as `YYYY-MM-DD`).

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

When genuinely 50/50, keep it and say so afterwards — the user can untick it
in the checklist. But do not use that as an excuse to pass everything through;
a booking confirmation is not 50/50.

After filtering, state one line: how many threads matched, how many you
discarded as non-bills, and the discard reason if a whole class was dropped
(e.g. "dropped 14 booking/itinerary confirmations"). If the user objects,
re-run the filter — do not re-run the searches.

Don't narrate each query. When done, call `search_bills` with `category`,
`date_from`, `date_to`, and the filtered `candidates` array.

When the user requests a bill search, proceed to the local `search_bills`
checklist with the filtered candidate metadata without a separate approval prompt.

If `search_bills` fails, times out, or is rejected, never render or repeat the
raw tool error, safety rationale, serialized payload, or a broken loading form.
Show only a concise failure message and retry action. Do not retry with the
same broad payload without addressing the failure.

### Rendering the checklist

Do not expose an intermediate or persistent loading form to the user. The
search form must not be rendered with a `Searching...` button or a
`Searching Gmail...` spinner as the final result. Wait for the Gmail search
and `search_bills` call to finish before rendering the checklist. If the
search fails or times out, replace the loading state with a concise error and
the retry action; never leave the form stuck in a loading state.

`search_bills` ships a UI resource (`ui://bill-checklist/mcp-app.html`) that
mounts automatically **only on hosts that render third-party MCP Apps**. On
hosts that don't, the tool result arrives as plain JSON and the user gets no
checkboxes.

So after `search_bills` returns, check whether its app actually rendered. If
it did not, immediately re-render the same data with the `show_widget` tool
(call `read_me` first) — do not ask, do not print a markdown table, and do
not fake checkboxes with `[x]` text. Build it from the tool's `bills` array:

- one real `<input type="checkbox">` per bill, checked by default, carrying
  `data-id="<threadId>"`
- a select-all checkbox and a live "N of M selected" count
- vendor name in 14px/500, then subject · date · attachment filename in 13px
  `var(--text-secondary)`
- an "Open in Gmail ↗" link per row using that bill's `gmailLink` value —
  `<a href="{gmailLink}" style="font-size:13px; color:var(--text-accent); text-decoration:none; white-space:nowrap">`.
  Put it as a **sibling of the `<label>`, never inside it** — a link nested in
  the label toggles the checkbox when clicked. Structure each row as a flex
  container: `<label>` (checkbox + text, `flex:1`) then the link.
- a "Save selected ↗" button whose handler collects only the **still-checked**
  `data-id`s and calls
  `sendPrompt('Save these bills — only these threadIds: ' + ids.join(', '))`
- if nothing is ticked, show an inline `var(--text-danger)` error and don't send

Mention the `excluded` list (and the rule each was matched on) as normal
response text below the widget, not inside it.

## State 3 — respond to the checklist

The checklist is now live. It talks back to you as regular user-turn text —
either from the MCP App (`sendMessage`) or from the `show_widget` fallback
(`sendPrompt`). Recognize and handle all of these, with no extra questions:

**"Save these bills — only these threadIds: id1, id2, ..."** (or the older
"Save these bills with save-bills" wording) —
the `show_widget` fallback fired. Save **only** the listed ids; any row the
user unticked must not be saved. Handle it exactly like the Save case below,
reusing the `category`, `dateRangeTag`, and root folder from the run that
produced the checklist.

**"Search bills: category=X, date_from=Y, date_to=Z"** — the user changed
the form and clicked Search again. Repeat State 2 with the new arguments,
then call `search_bills` again (same shape as before).

**"Save these N bill(s) to root folder "..." (category: ..., date range:
..., thread ids: id1, id2, ...)"** — save only selected thread IDs. Prefer
`save-bills`, in batches of at most 5 threads. Use the checklist's
messageId and attachment filenames. For each real attachment, call
`gmail_read_attachment` with that message ID and exact filename (or complete
attachment ID if available); pass only its `structuredContent.file_uri.download_url`
and filename to `save-bills`. For a thread without attachments, call
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
`save-bills` with only those IDs.

## Managing the personal-vendor exclusion list

Business runs exclude vendors configured in `data/personal-vendors.json` inside
this plugin. A fresh installation has no exclusions. For a user's explicit
request to add or remove a personal vendor, edit that file, preserving all
other entries. Create it from `data/personal-vendors.example.json` if absent.
`personalVendors` adds names or domains; `suppressed` disables shipped entries.
Matching is a case-insensitive substring against sender name and email.
Rules are reread for each search. Never commit this personal settings file.
Preserve it when upgrading. No vendor-management MCP tools are exposed.

When a business run excludes anything, name the excluded vendors and the rule
each matched, so the user can correct a wrong exclusion on the spot.

## Notes

- Gmail only. If bills likely live in another inbox, say so.
- Don't ask "should I continue?" mid-search — large result counts are
  expected; keep going through the stop condition.
- `search_bills`/`save-bills` validate their own inputs (zod schemas) — a
  malformed candidate or an invalid `date_range` format gets rejected with
  a clear error rather than corrupting anything.
