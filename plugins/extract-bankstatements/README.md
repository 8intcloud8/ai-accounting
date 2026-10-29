# Bank Statement Extractor

Local skill plugin for extracting CSV, Excel, and text PDF bank statements into `date,description,debit,credit,file` CSV. SQLite storage is created automatically using Python’s built-in `sqlite3`; no database server or cloud backend required.

## Install

Register this folder as a local plugin in your assistant host. The plugin includes Codex and Claude manifests, a skill, and mapper/extractor/validator agent instructions. Agent orchestration depends on host support.

Install Python dependencies in your environment:

```sh
python3 -m pip install -r requirements.txt
```

## Use

Ask: “Extract my bank statements.” The skill asks which folder contains the statements and which financial year to process. It validates extracted files, saves the combined CSV, and prints counts, dates, money in/out, balances, reconciliation issues, and the CSV location in chat.

An explicit single-file test processes that file directly. Source files are preserved. Personal categorisation rules are not bundled.

## PDF support

Text-based NAB Transaction Listing PDFs are automatically recognised by their printed headings. Extraction retains multiline descriptions and checks all running balances and summary totals using decimal arithmetic. The inspected NAB sample produced 58 verified transactions.

Other PDF layouts use generic table extraction and require independent validation. Scanned PDFs require OCR; OCR is not included. `.xls` binary files are not supported by openpyxl; convert to `.xlsx` or CSV first. Bank movements are not automatically classified as taxable income or deductible expenses.

## Internal persistence

Requires Python 3.10 or newer.

Approved imports are saved automatically in `~/.ai-accounting/accounting.db`, reused across Codex sessions. Users provide a statements folder and account identity, not database setup. `AI_ACCOUNTING_DB` can select a separate local workspace internally.

Storage includes accounts, transactions, import history, and source links. Money uses integer cents. Reimports of the same source are skipped; changed extraction of an existing source is rejected pending correction. Identical repetitions within a source are preserved. Matching transactions in a different source block that entire import for review: without bank IDs, the plugin cannot safely distinguish overlaps from separate identical payments.

The store exposes `import`, `summary`, `transactions`, and `export` commands. Only approved rows may be imported. Summaries and exports can be filtered by account and ISO date range. CSV exports never overwrite existing files. Generated CSVs must not be reimported as statements.

Invoice extraction, payment matching and running-cost allocation are separate plugins: `extract-invoices`, `match-payments`, and `allocate-running-costs`. Each has one skill and bundles compatible storage helpers. All reuse the same database. Preserve source documents: storage retains references, not document copies.

## Scripts

Scripts live in `skills/extract-bankstatements/scripts/`:

- `inspect_statement.py`: inspect source headers and sample rows.
- `extract.py`: extract transactions using a mapping.
- `nab_pdf.py`: NAB listing parser and reconciliation checks.
- `accounting_store.py`: automatic SQLite imports, retrieval, summaries, and CSV exports.
- `validate.py`: validate extracted rows.

Dependencies retain their own licenses. See the repository license.
