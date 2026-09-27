---
name: save-bills
description: Save selected Gmail bills, invoices, or receipts to disk using temporary attachment links returned by the connected Gmail MCP. Use after bill candidates have been selected.
metadata:
  version: "1.0.0"
---

# save-bills

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
