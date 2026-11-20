---
name: setup-accounting
description: Configure the local accounting workspace and business profile once, then show next steps.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# Set up Accounting

On Windows, run every `python3` command in this skill as `py -3` (or `python` if `py` is missing).

## Check the computer first

Before any question, run `python3 scripts/check_environment.py status` (paths are relative to this skill). It prints JSON; `messages` are already in plain words for the user.

- `python_ok` false, or the command fails to start: give the Python message (download from python.org/downloads, then start a new chat) and stop.
- `missing_packages` not empty or `windows_servers_ok` false: give its message and ask "OK to install?" On a yes, run `python3 scripts/check_environment.py install`. It needs the internet and writes to a private folder in the Codex home, so request approval for that one command. If it fails, pass on its message. When it returns `restart_codex` true, tell the user to quit and reopen Codex, then continue.
- `email_ready` false: give the Node message once. Email search and save stay unavailable until Node is installed; continue with everything else.
- `ready` true: say nothing about the check and continue.

Never install anything into the system Python, and never ask the user to open a terminal.



Ask for the accounting folder, legal business name, entity type and stable business ID. Reuse known details. Ask whether GST registered and cash/accrual basis; unknown stays null/unknown. One business per workspace. Support AUD initially.

Ask once for the root folder (the workspace); never ask for separate input or output folders. Setup creates inside it `bankstatements/` (user drops statements here), `invoices/` (bills, invoices, receipts), `output/` (all reports and exports, under `output/YYYY-MM-DD/reports/`), plus internal `db/`, `documents/` (verified copies) and `backups/`. Tell the user the three folder paths. Use `scripts/accounting_store.py --db <folder>/db/accounting.db setup-accounting --request <profile.json>`; paths are relative to this skill. Profile example:
```json
{"business_id":"example-business","legal_name":"Example Business","entity_type":"sole_trader","gst_registered":null,"gst_basis":"unknown"}
```
Never assign a guessed GST basis. Existing populated workspaces must retain their existing business ID. A second business needs another workspace. Pass `--db <workspace>/db/accounting.db` on every subsequent command in this chat; there is no machine-wide default, and setup registers the folder so later chats can offer it. Show the folder and next input needed; users do not administer SQLite.

Plugins are normally added from the Codex plugin list, which needs no installer. The maintainer script `scripts/install.py` in the source repository is only for installing from a local checkout. Never claim setup is complete until the check below reports ready and plugin paths resolve.

If GST settings were initially unknown, use `update-profile --request <JSON>` with gst_registered, gst_basis and a reason. Existing reviewed GST entries must be reversed/reviewed before changing tax settings.

## Local server (page buttons)

The review pages have buttons (Save selection, Choose folder, move to quarantine) that Codex blocks by default. Run `scripts/enable_local_server.py status`. If `on` is false and `asked` is false, ask once, in these words:

> Turn on the buttons in the review pages? Without them you copy a line from the page and paste it into the chat. Turning them on lets commands Codex runs use the internet. You can turn it off later.

- Yes: run `scripts/enable_local_server.py on`. It edits the Codex config outside the workspace, so request approval for that one command. Then say: "Done. Quit and reopen Codex to finish." If it prints hand-edit instructions, pass them on as written.
- No: run `scripts/enable_local_server.py decline` and do not ask again. Everything still works by copy and paste.

Never turn it on without a yes. To turn it off later: `scripts/enable_local_server.py off`.

## Confirm reporting scope

Run `configure-reporting --request <JSON>` after verifying the BAS reporting method and all relevant bank/card account names. Example: `{"method":"simpler","expected_accounts":["CBA business","Credit card"],"gst_turnover_under_10m":true,"evidence":"User confirmed reporting method and full account inventory"}`. Always record `gst_turnover_under_10m` (work it out from the last 12 months of sales and the ATO-registered method, then confirm): Simpler BAS and cash basis are only available under $10 million. Supported methods are simpler/full/instalments/unknown; only confirmed simpler can pass this version's BAS scope gate. Do not invent eligibility from GST registration. Missing expected account-period evidence blocks readiness. The package reports G1 GST-inclusive; communicate that convention. PAYG and other labels remain separate checks.

## Which BAS sections apply

Ask once, after the profile is saved, in these words:

> Do any of these apply to your business? Most small businesses answer no to all.
> - Paying wages or withholding tax from workers' pay
> - PAYG instalments (the ATO sends you an instalment amount each quarter)
> - Fringe benefits tax paid by instalments
> - Fuel tax credits
> - Wine equalisation tax
> - Luxury car tax
> - Deferring GST on imported goods

Save every answer with `save-bas-registrations --request -`: `{"business_id","answers":[{"topic","answer":"yes|no|unknown","evidence":"User confirmed at setup","provenance":"user_confirmed"}]}`. Topics: payg_withholding, payg_instalments, fbt_instalments, fuel_tax_credits, wine_tax, luxury_car_tax, deferred_import_gst. A no is saved for the business and those sections are skipped on every BAS. A yes is asked again each BAS for that period's figures. "Not sure" stays unknown. If the answer later changes, save it again; the latest answer wins.

## Identify the BAS work required

Reuse saved period applicability. Route missing or stale applicability facts to `tax-intake`; it owns the period interview and persistence. Validate its saved results before reporting readiness; do not repeat the interview here.

## Showing transactions

Whenever you show the user bank transactions (any list: "show me these", a payee group, the unclassified ones), run `export-transactions --start --end` with `--ids 12,15,...` for just those transactions (for the whole period, link the live `output/BAS live/<start> to <end>/BAS workbook.xlsx` instead: every change rewrites it). It writes an Excel workbook in `output/` with a Summary by payee and one row per transaction showing its status (Classified, Proposed, Not classified), category and GST. Give the user the workbook link, plus a short grouped summary in chat (count and total per payee group). Never paste a table of more than 10 transactions in chat. For proposals the user will approve in Excel, use `export-proposals` instead: its Decision column can be applied back.

## Keep working; stop only when you need the user

Work like Claude Code: do the work, keep going, and stop only when you need the user.

1. Commands that change the books return `next_step`. When `keep_going` is true, do `do_next` straight away, without asking permission, and carry on. When it is false, stop: say in a sentence or two what you did, ask everything you need in that one message (numbered, each with your best answer from the records), and make `end_your_reply_with` the last line, word for word. If a command returned none, run `workflow-status --start --end` and decide the same way.
2. Never show step numbers, step lists or progress summaries. The chat is the one place the user looks: results and decisions go there.
3. Ask only for what only the user can give: facts, missing documents, and the OK to post. Never ask "shall I…" for work you can do.

Never end a reply with a promise such as "I'll continue with…", "Next I'll…" or "I'll now…". Your turn has ended and nothing happens. Do that work now instead.

Never call anything pending, blocked, under review or unresolved without saying in the same sentence what resolves it and who does it, for example: "$2.73 OpenAI GST is pending: check the invoice; an ARN means no credit, an ABN means claim it." When posting GST as pending, `gst.resolve` must say exactly that; the command refuses pending GST without it.

When nothing is open, prepare the BAS draft and show it.

## Passing input to commands

Commands that take `--request`, `--records`, `--rule`, `--confirmed` or `--approved` read JSON from stdin when given `-`. Pipe the JSON in (`... --request - <<'JSON'` … `JSON`) instead of writing request files: every file you write is shown to the user as an edited file. Send several documents in one call where a command accepts a list, for example `record-supporting` with `{"documents": [...]}`.
