---
name: save-invoices
description: Save selected Gmail bills, invoices, or receipts to disk using temporary attachment links returned by the connected Gmail MCP. Use after bill candidates have been selected.
metadata:
  version: "1.0.0"
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# save-invoices



Save only the bills selected by the user. Use `save_invoices` in batches of at
most five threads. A checklist request lists `message ids` aligned with its thread ids: save
that message's documents (the thread's latest message with attachments). Fetch each batch's
download links just before its call, because they expire.

Save into the accounting workspace chosen in this chat: `root_folder` is the request's folder,
normally `<workspace>/invoices`, so files land in `<workspace>/invoices/<Category>/<date range>/`
with `manifest.csv`, where invoice extraction reads them. When fulfilling an email checklist save
request, persist its rendered HTML at `<workspace>/output/<YYYY-MM-DD>/reports/email-invoices-<run-id>/index.html`
(for a folder outside a workspace: `<folder>/reports/email-invoices-<run-id>/index.html`). Use the current run's preview. Create missing directories,
verify the copy, and include its path with the save result. Reuse the same
report on retries. If the preview is unavailable, report that separately.

For each attachment, call `gmail_read_attachment` with the exact Gmail message
ID and complete attachment ID when available, otherwise the exact filename.
Pass only `structuredContent.file_uri.download_url` and the filename to
`save_invoices`.

For a thread without attachments, call `gmail_read_email(format="full")` once.
Traverse nested MIME parts and take `text/html`, falling back to `text/plain`.

Construct each item as
`{threadId,date,vendor,subject,foundVia,attachments,html?,text?}`. Never request
raw MIME. Never print email bodies, signed URLs, or attachment bytes into model
output. When tool orchestration is available, collect Gmail results and call
`save_invoices` inside it, exposing only final counts and failures.

Signed links expire. Save promptly and retry failed items only with fresh
links. If the Gmail connector cannot provide temporary file links, report that
saving is unavailable; never relay raw MIME or PDFs through the model.

## Failures and recovery

- The save tool attempts each attachment download or inline PDF conversion,
  then retries that file once on failure. It verifies non-empty writes and
  removes partial files from failed attempts. Successful files remain saved.
- Read the returned `saved`, `failed`, `savedCount`, and `failedCount` fields.
  Report verified saved-file counts, failures with reasons, the destination
  folder and manifest location. Count files separately from selected threads;
  one thread can contain several invoices or receipts. Never report a failed
  or unverified item as saved.
- `manifest.csv` is appended in the destination folder with a `saved` or
  `failed` status for each attempted file. Failure reasons come from the tool
  result. Keep previous manifest rows and successful downloads.
- For a failed attachment, obtain a fresh Gmail download link and retry only
  that attachment once through the save tool. For a failed inline conversion,
  retry only that message. Resolve failures to their source message and file;
  use the manifest when a thread was partially saved. Do not resubmit its
  successful attachments. Filename deduplication prevents overwrites but does
  not prevent duplicate documents when a whole batch is submitted again.
- If a tool call times out or errors without a result, inspect the destination
  and manifest before retrying: files may already have been written. If the
  outcome cannot be verified, report it as unverified rather than assuming
  nothing was saved or repeating the whole batch.
- If fresh-link recovery also fails, stop retrying that item and report the
  remaining failure and next action. Continue independent selected items when
  possible. If Gmail cannot provide temporary links or the save tool is
  unavailable, report the blocker and retain the selections for a later retry.
