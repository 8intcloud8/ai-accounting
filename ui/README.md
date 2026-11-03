# Shared invoice checklist styling

`checklist.css` is the canonical compact-table style for Search Email Invoices
and Review Invoices. Edit it here, then run `python3 scripts/build_release.py`
to synchronize the standalone plugin copies before building the email app.
Do not edit those generated copies independently.

Both views share fonts, light/dark colours, table spacing, checkbox and selection
states, search fields, badges and primary buttons. Columns and action wording
remain specific to saving email invoices or quarantining reviewed local files.
