---
name: save-invoices
description: Save selected Gmail bills, invoices, or receipts to disk using temporary attachment links returned by the connected Gmail MCP. Use after bill candidates have been selected.
metadata:
  version: "1.0.0"
---

# save-invoices

## Official guidance for tax and regulatory decisions

Read `references/official-sources.md` when this task requires tax or regulatory interpretation. Use live official guidance, cite exact sources and access dates, and report access failures explicitly. Routine extraction/matching does not establish GST or deduction eligibility.

Save only the bills selected by the user. Use `save_bills` in batches of at
most five threads.

For each attachment, call `gmail_read_attachment` with the exact Gmail message
ID and complete attachment ID when available, otherwise the exact filename.
Pass only `structuredContent.file_uri.download_url` and the filename to
`save_bills`.

For a thread without attachments, call `gmail_read_email(format="full")` once.
Traverse nested MIME parts and take `text/html`, falling back to `text/plain`.

Construct each item as
`{threadId,date,vendor,subject,foundVia,attachments,html?,text?}`. Never request
raw MIME. Never print email bodies, signed URLs, or attachment bytes into model
output. When tool orchestration is available, collect Gmail results and call
`save_bills` inside it, exposing only final counts and failures.

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
