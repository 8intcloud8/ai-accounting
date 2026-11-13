# ATO library

ATO guides that ship with the plugins. The agent searches them first (`ato-search`) and must
cite a guide, page and exact quote, which the code checks word for word.

Add a guide (PDF, saved HTML page, .md or .txt):

    python3 accounting_core/accounting_store.py ato-add --file <guide.pdf> \
      --title "GST for small business" --url https://www.ato.gov.au/... \
      --issued 2026-07-01 [--applies-from 2026-07-01 --applies-to 2027-06-30]

Or drop files here and run `ato-sync` (then add titles/URLs with `ato-add` on the same file).

`library.json` holds the extracted text and details; `scripts/build_release.py` copies it into
every plugin. Originals stay here. Scanned PDFs need OCR first. Commit both the guide and library.json.
