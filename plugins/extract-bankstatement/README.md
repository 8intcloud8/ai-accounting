# Bank Statement Extractor

Local skill plugin for extracting CSV, Excel, and text PDF bank statements into `date,description,debit,credit,file` CSV. No database or cloud backend required.

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

## Scripts

Scripts live in `skills/extract-bankstatement/scripts/`:

- `inspect_statement.py`: inspect source headers and sample rows.
- `extract.py`: extract transactions using a mapping.
- `nab_pdf.py`: NAB listing parser and reconciliation checks.
- `validate.py`: validate extracted rows.

Dependencies retain their own licenses. See the repository license.
