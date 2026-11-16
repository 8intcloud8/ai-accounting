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

## Check the computer first

Before any question, run `python3 scripts/check_environment.py status` (paths are relative to this skill). It prints JSON; `messages` are already in plain words for the user.

- `python_ok` false, or the command fails to start: give the Python message (download from python.org/downloads, then start a new chat) and stop.
- `missing_packages` not empty: give its message and ask "OK to install?" On a yes, run `python3 scripts/check_environment.py install`. It needs the internet and writes to a private folder in the Codex home, so request approval for that one command. If it fails, pass on its message.
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

## Always end with the next step

Never finish a reply by saying work "remains open" or "is not ready" without saying what it is and what happens next. After any change, correction or answer:

1. Run `workflow-status --start --end` for the period.
2. In the reply itself (not only in a linked file), list each open step on its own line, lowest first, saying what is open and where it gets fixed, for example: "Step 4 Transactions: 12 payments still need a category (I'll show them grouped by payee)." or "Step 6 Reconciliation: the September closing balance doesn't match the statement by $40."
3. End with one question that starts the first item: "Shall I start Step 4: Transactions now?" If the user has said to keep going, start it instead of asking.

Never end a reply with a promise such as "I'll continue with…", "Next I'll…" or "I'll now…". The user sees that as work in progress, but your turn has ended and nothing happens. Either do that work now, in the same reply, and report it when done, or stop and ask the question in step 3. Only stop when you need the user's answer or the period has nothing open.

If nothing is open, say so and offer the next stage. Use the step names from the BAS walkthrough (1 Setup, 2 Bank statements, 3 Invoices, 4 Transactions, 5 Payroll and BAS items, 6 Reconciliation, 7 BAS draft).

## Passing input to commands

Commands that take `--request`, `--records`, `--rule`, `--confirmed` or `--approved` read JSON from stdin when given `-`. Pipe the JSON in (`... --request - <<'JSON'` … `JSON`) instead of writing request files: every file you write is shown to the user as an edited file. Send several documents in one call where a command accepts a list, for example `record-supporting` with `{"documents": [...]}`.
