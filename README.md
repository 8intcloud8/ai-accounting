# AI Accounting

Bookkeeping and BAS preparation for Australian small businesses, done for you in a chat with Codex. You give it your bank statements and invoices; it sorts the transactions, works out the GST and prepares your BAS figures, and asks you only when it needs you.

Everything stays on your computer. It does not lodge anything with the ATO: you check the figures and lodge them yourself (or your accountant does).

**You need:** a Mac and the Codex app. Installing takes about 5 minutes.

## Install

1. **Install Codex** from [openai.com/codex](https://openai.com/codex/), open it once and sign in. Then quit it.
2. **Open Terminal**: press `⌘ Command` + `Space`, type `Terminal` and press `Return`.
3. **Copy this line, paste it into Terminal and press `Return`:**

   ```sh
   curl -fsSL https://raw.githubusercontent.com/8intcloud8/ai-accounting/main/scripts/install.sh | sh
   ```

   - If a window asks to install **developer tools**, click **Install**, wait until it finishes, then paste the line again.
   - If it says to install **Python**, go to [python.org/downloads](https://www.python.org/downloads/), download the macOS installer, open it and click through.

4. When Terminal says **Done**, close it. Open Codex, start a new chat and type:

   > **Set up my accounting**

   Codex asks for your business details and where to keep your files, then takes it from there.

## Using it

Just ask in the chat, in your own words. For example:

- "Set up my accounting"
- "Here are my bank statements" (then drop the PDF or CSV files into the chat)
- "Find my invoices in Gmail for July to September"
- "Do my BAS for July to September"
- "Show my BAS"

**Show my BAS** opens an interactive view right in the chat: the amount to pay, the BAS labels (G1, 1A, 1B, W2), what is still to do, and a **Transactions** tab where you can change a category and press **Save**. Every figure can be checked in the BAS workbook (Excel) it keeps up to date.

Codex keeps working by itself and stops only when it needs something from you: a fact only you know, a missing document, or your OK before it records something.

## Your files

When you set up, you choose a folder (for example `Documents/Accounting`). Inside it:

| Folder | What goes there |
|---|---|
| `bankstatements` | Your bank statements |
| `invoices` | Your invoices and receipts |
| `output` | Your BAS workbook, dashboard and reports |
| `backups` | Automatic backups |

Keep this folder private: it holds your financial records. Back it up like any important folder.

## Update

Paste the same line from step 3 into Terminal again, then quit and reopen Codex.

## If something goes wrong

- **"Codex was not found"**: install Codex, open it once, then run the line again.
- **Codex doesn't know about accounting**: quit Codex completely (`⌘ Command` + `Q`), open it again and start a new chat.
- **Anything else**: tell Codex what happened in the chat, or [open an issue](https://github.com/8intcloud8/ai-accounting/issues). Never post your statements, invoices or tax details in an issue.

## Good to know

- Gmail is only connected if you ask Codex to search your email for invoices. Xero is optional.
- Codex checks tax and GST questions against current ATO guidance and tells you where each answer comes from. Treat its BAS as a draft for you or your accountant to review.
- Beta: Mac only for now.

---

## For developers

Install from a local checkout (maintainers):

```sh
python3 scripts/install.py --workspace "/path/to/Accounting" --profile profile.json --dependencies
```

Finds Codex on `PATH` or inside the Codex app. `--dependencies` installs the Python packages (`pdfplumber`, `openpyxl`) into a private folder in the Codex home and builds the Gmail plugins (needs Node.js). Use `--local-only` to skip the Gmail plugins and `--local-server yes|no` to answer the page-buttons question. Profile fields: business_id, legal_name, entity_type (company/sole_trader/trust/partnership), gst_registered (true/false/null), gst_basis (cash/accrual/unknown). Open a new chat after installing.

`scripts/install.sh` is the one-line installer above: it adds this repository as a Codex plugin marketplace and installs every plugin in it.

### BAS view in the chat

The `manage-accounting` plugin includes the `bas` MCP server (`accounting_core/bas_mcp.py`, standard library only). Its `show_bas` tool renders `bas_view.html` inline in the Codex chat as an MCP App. `save_transaction_edits` saves category changes from its table: same-kind account swaps reverse and repost the journal; anything that can affect GST is sent to Codex in the chat. The live `Dashboard.html` and `BAS workbook.xlsx` are rewritten after every change in `<workspace>/output/BAS live/<start> to <end>/`.

## Plugins

| Plugin | Role |
|---|---|
| setup-accounting | Workspace and business setup |
| ato-docs | Research official ATO guidance with citations and year/entity checks |
| tax-intake | BAS scope and tax-return intake questions; coverage validation pending |
| setup-xero-mcp | Optional Xero OAuth setup and automatically refreshed MCP connection |
| manage-accounting | Resume a period, show the BAS view and what is outstanding |
| search-email-invoices | Find Gmail documents |
| save-invoices | Save selected documents |
| review-invoices | Review duplicates and non-invoices; quarantine approved files |
| upload-invoices-drive | Store invoices in Google Drive invoices/YYYY-MM folders |
| extract-bankstatements | Extract/import bank transactions |
| extract-invoices | Extract/import invoice evidence |
| match-payments | Propose and confirm payment links |
| allocate-running-costs | Apply business-use allocations |
| classify-transactions | Post balanced ledger entries with GST evidence (Xero-style Australian chart of accounts) |
| reconcile-accounts | Reconcile statement opening/closing balances |
| prepare-bas | Draft G1/1A/1B GST workpaper |
| prepare-tax-report | Trial balance and annual accounting workpaper |

Each plugin has one skill. All reuse the same local workspace. Gmail search/save are optional. No Xero account is required.

## Workspace

```text
Accounting/
  db/accounting.db
  documents/<hash-prefix>/<hash>.<extension>
  output/YYYY-MM-DD/reports/
  output/BAS live/<start> to <end>/
  backups/
```

One business per workspace. Money uses integer cents. Imports retain source hashes; managed copies survive original-file moves. Move the complete workspace together and update the workspace selector when relocating it. CSV/JSON reports are for review; SQLite is internal assistant state.

Use `AI_ACCOUNTING_DB` to explicitly select a workspace database, or the installer-managed `accounting-workspace.json` in Codex home. Existing legacy installations keep their previous default unless explicitly configured.

## Corrections and backup

The workflow supports audited withdrawal/reimport of invoice extraction, reversing payment matches and allocations, and offsetting journal reversals. Reverse dependent records first. Source documents and correction history remain available. Report snapshots are historical; regenerate after changes. Workflow review checkpoints are invalidated when accounting data changes.

`backup-workspace` creates a consistent database/evidence ZIP; `restore-workspace` requires a new destination. Backup files contain private financial data. Keep them locally in a suitable location.

## Supported scope

This is a beta accounting workpaper product. It does not lodge BAS or income-tax returns. BAS output covers reviewed GST and PAYG withholding labels; special GST schemes require additional work. Tax output is a bookkeeping workpaper, not tax payable or a complete statutory return. Accrual recognition requires reviewed entries and explicit attribution evidence. Opening balances and year-end adjustments must be entered before relying on full accounts. Cash partial payments use confirmed payment links and bounded per-invoice GST allocations. Multiple invoices in one journal require explicit invoice_tax_allocations. Mixed-use allocations must match the GST basis and attribution period.

## Development and release

`accounting_core/` is the sole maintained Python accounting runtime. `scripts/build_release.py` synchronizes it into the separate plugins, validates their one-skill structure and writes the local marketplace. Never edit generated runtime copies independently.

```sh
PYTHONPATH=accounting_core python3 -m unittest discover -s tests -v
python3 scripts/build_release.py --output /tmp/ai-accounting-release
```

Release builds must also build the two Node MCP plugins. CI runs storage/workflow tests on macOS and Linux, validates bundled parity, and tests Node plugins. Run fresh-install validation before public distribution.

MIT licensed. Never commit private statements, invoices, credentials or database files.

## Review tables in Codex

Accounting skills show review CSVs as a local table beside the chat: search, sort, filter issues, read formatted amounts, open managed source documents and save check/correction requests. CSV exports remain available. The view runs only on this computer and needs no cloud service or additional Python package.

```sh
python3 accounting_core/accounting_store.py --db /path/to/accounting/db/accounting.db review-table --csv /path/to/accounting/output/YYYY-MM-DD/reports/invoice-review.csv --title "Invoice review"
```

Open the returned review_url in Codex's browser panel. Keep the command running while reviewing; stop it with Ctrl-C afterwards. Requests are saved as dated JSON workpapers with original row values and the CSV hash. Ask Codex to review and apply them through audited accounting commands. The table itself never edits SQLite or silently approves tax treatment. Source links serve only existing managed files under that workspace's documents folder.

## Official guidance lookup

Every skill packages topic-specific official-source references. Before tax or regulatory decisions, Codex searches and reads applicable ATO guidance (or ASIC/Fair Work for the relevant obligations), cites exact URLs and access dates, and retains source notes with the draft workpaper. Failed access is disclosed and dependent treatment remains pending. Routine extraction and matching can continue.

Browsing/search is supplied by the host, not installed by this package. These instructions do not add a tax/payroll engine or a scheduled crawler. Rebuild the suite to distribute changed references; existing installed caches are not updated by editing source files alone.
