# Review Invoices

One skill for reviewing a local folder before invoice extraction. It identifies
identical files, possible duplicate documents, non-invoices and unreadable files.
It preserves receipts, credit notes, sales invoices, RCTIs and supporting evidence.

Ask: **Review invoices in /path/to/folder. Show duplicates and non-invoices.**

The first run opens a searchable review page without moving anything. Tick files,
choose **Move selected to quarantine**, inspect the selection and confirm. The
local helper verifies hashes, moves only selected files and saves a JSON recovery
log. **Undo this move** restores them without overwriting existing files.
Manifests, invoice CSV exports, databases and managed accounting evidence are
protected. Invoices selected for exclusion require a reason.
Permanent deletion and accounting database changes are outside this skill.

No additional server, database or cloud connection is needed. PDF reading and OCR
use tools already available in the host; unavailable extraction is reported.
