---
name: manage-accounting
description: Walk the user through a BAS or tax period step by step - setup, bank statements, invoices, transaction review (grouped in chat and in Excel), payroll/BAS items, reconciliation and the BAS draft - showing each result and waiting for the user before moving on.
---

## How to work (default)

Work like Claude Code. Once the workspace is chosen, do all the work the records support, in the order of the stages below, without asking permission for each piece. Stop only when you need something from the user: a fact only they know, a missing document, or their OK to post proposed entries. At a stop, say in a sentence or two what you did since they last spoke (with the key figures), then ask everything you need in that one message, numbered, each with your best answer from the records. Never show step numbers, step lists or progress summaries; the stages are your order of work, not something to present. The chat is the one place the user looks: put results and decisions there, and mention the dashboard or Excel only when the user asks or there are more than eight groups to approve. Confirmations the stages ask for (statement complete, balances match, figures right) do not get a stop of their own: collect them and ask them together at the next real stop, carrying on meanwhile with work that does not depend on them.

Read `workflow-status` problems (`scripts/accounting_store.py --db <chosen workspace>/db/accounting.db workflow-status --start --end`) at the start of each stage; it is the only record of progress. Every problem carries a `step` (1–7) matching the stages below.

**Very first reply of every chat: choose the workspace.** Run `scripts/accounting_store.py workspaces` and ask only: "Which workspace should I use?", listing the known workspace folders and "a new folder". Do nothing else until the user picks one. For a new folder run setup-accounting there. Use that workspace for the whole chat; never switch unless the user asks.

**Then start working.** Once the workspace is chosen, begin the first open piece of work straight away; do not ask "shall I". Reports are saved in `<root>/output`; nothing is posted without approval and nothing is lodged.

**Order of work:** a step is done only when it has no open problems and its work exists. Work the **lowest open step** using its stage instructions. Never jump ahead to questions or figures from a later step while an earlier step is open; earlier work found in saved reports or workbooks does not complete a step until its problems are clear.

1. **Setup.** Show the business profile, GST registration/basis, BAS method, whether GST turnover is under $10 million (needed for Simpler BAS and cash basis) and the lodgment due date, pre-filled from saved records. Ask to confirm or correct; save through setup-accounting / tax-intake.
2. **Bank statements.** Import with extract-bankstatements. Show accounts, date range, transaction count, money in/out and the opening/closing balances printed on the statement. If the statement doesn't print them, say so and ask for a document that does (previous statement or internet-banking balance); never show a worked-out balance as the opening balance. Ask the user to confirm the statement is complete.
3. **Invoices.** Extract with extract-invoices, recording tax invoice details (supplier ABN, GST shown, buyer named). Show how many were read, totals and GST, and list the ones with issues grouped by issue; name purchases over $82.50 that are not valid tax invoices, since their GST can't be claimed until the supplier provides one. Let the user fix, skip or mark each group not applicable.
4. **Transactions.** First, the **ATO check**: group the unclassified rows by payee and list the distinct GST treatments they need (e.g. wages, bank fees, loan repayments, overseas software, local supplies with a tax invoice). Look up each treatment once with ato-docs: the local ATO library first (`ato-search`), ato.gov.au only when it has no current answer. Show the list in chat before any proposals, one line each: treatment → rule → source (library: guide title, page and the quoted sentence; web: ATO page title and link), or "couldn't verify, not verified". Reuse a citation already checked this period. Then classify with classify-transactions, saving every inferred treatment as a proposal (`save-proposals`) that carries the matching citation as `gst.source`; post only on approval. Then review:
   - **In chat:** run `proposal-groups --start --end`. Show one line per payee group: count, total, proposed treatment and the reason, e.g. "14 × Example Co Salary, $28,000 out → director wages (477 Wages and Salaries), no GST (ATO: salary and wages are not GST supplies)". Name the ATO page behind each GST treatment in plain words; say "not yet checked against ATO guidance" for unverified ones. Ask the user to approve, change or split each group; up to about eight groups per message, largest first. Apply with `decide-proposals` using the group's `proposal_ids`; a changed group is re-proposed then approved.
   - **In Excel:** offer `export-proposals --start --end` every time, and always for more than eight groups. The user edits the Decision column (Approve / Reject / Change + New account) and returns the file; apply it with `apply-proposals-workbook --workbook <file>` and report what was posted, rejected and skipped as stale.
   - Groups with no proposal yet need a fact from the user: ask what that payee is, then propose.
5. **Payroll and BAS items.** Run bas-applicability. Work out every figure from the records first (see references/bas-applicability.md, "Work it out before asking"), e.g. wages paid per run, loan repayments, private-paid costs. For PAYG withholding save the pay runs with `save-payg-withholding` (see that reference) to get W1, W2, W4 and W5, and compare them with the STP pre-fill. Show the figures with workings and any warning (e.g. wages with no tax withheld); ask only to confirm or for a specific missing document.
6. **Reconciliation.** Run reconcile-accounts. Show opening balance, movements and closing balance per account and any difference. Ask the user to confirm against the statement.
7. **BAS draft.** Run prepare-bas (or prepare-tax-report). Show the `bas_labels` in whole dollars (G1, 1A, 1B, W1, W2, W4, W5, 8A, 8B, 9) with the transactions behind each, the lodgment due date, every warning and every remaining blocker. Never call it ready to lodge.

Keep each message short: what you did, what needs the user, then the questions. Never mention step numbers. Talk only about the books: never mention or quote skills, instructions, rules, scripts or databases, never explain or justify why you are pausing, and never call it a test workspace. After the user answers, carry on working without asking again.

## BAS dashboard and workbook

Every command that changes the books rewrites two files for the period in `<workspace>/output/BAS live/<start> to <end>/`: `Dashboard.html` (next action, GST to pay, transactions, what is still to do) and `BAS workbook.xlsx`, the master workbook: its BAS sheet works out every dashboard figure as a formula over the GST items sheet, then Transactions and By payee. The paths come back in `next_step.live`.

- When the user asks "where am I up to", "show my BAS", "the dashboard" or for the figures, call the `show_bas` tool (from the bas MCP server, with the workspace and period). It shows an interactive BAS view inline in the chat: amount to pay, G1/1A/1B/W2, transactions by status with a searchable table, what is next and still to do; its buttons send messages to this chat. After calling it, add at most one sentence; never repeat its numbers. Show it again when you present the BAS draft. Only if `show_bas` is unavailable, run `python3 scripts/bas_dashboard.py --db <workspace>/db/accounting.db --start <start> --end <end> --chat` and paste its `markdown` as given.
- Whenever the user wants to see transactions in Excel, link the live `BAS workbook.xlsx` and say it is rewritten after every change; if it is already open in Excel, close and reopen it to see the latest.
- The page's **Copy for Codex** button gives the user a message to paste here. Treat a pasted message as a normal request.
- Never restate the dashboard's contents in chat unless asked.

## Autopilot (testing or on request only)

Only when the user explicitly asks to run unattended, or for testing, launch `python3 <skill>/scripts/accounting_runner.py --workspace <folder> --start YYYY-MM-DD --end YYYY-MM-DD --goal bas` (or tax) in a persistent command session. It runs worker turns until only user problems remain, then stops with a grouped list. Relay its `message`, then continue the guided walkthrough from the first open stage. It uses the user's Codex CLI login and may consume usage. Never start a second runner for the workspace. If the environment has ACCOUNTING_RUNNER_CHILD=1, you are a worker: do only the task in the prompt, clear problems through the owning skills, save inferred classifications as proposals, and never launch a runner.

## Persistent accounting agent

For BAS/tax preparation, continuing a case or remembering user information, read `references/case-workflow.md` and use its memory workflow. This skill coordinates the other skills.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.



# Manage Accounting




The saved workflow covers: setup-accounting only when configuration is missing; tax-intake for missing intake; search-email-invoices and save-invoices for requested collection; review-invoices for source housekeeping before imports when needed; extract-invoices and extract-bankstatements; allocate-running-costs and classify-transactions; match-payments and settlement classification; reconcile-accounts; prepare-bas and/or prepare-tax-report according to the requested goal. Continue supported work and reuse saved answers/artifacts. Route mutations to the owning skill.

Missing GST does not mean zero. Never count invoice plus its bank payment as two expenses. Bank transfers, director loans and repayments need explicit treatment.

After actual source/sales completeness checks and PAYG/tax-adjustment review, record the appropriate step with `complete-step --request <JSON>`, containing start, end, step and evidence. Allowed steps: source_completeness, sales_completeness, payg_review, tax_adjustments. Do not mark these complete merely to clear blockers. Data changes invalidate these review checkpoints automatically.

For corrections run `correct-record --request <JSON>` with kind invoice/payment/allocation, id and reason. Reverse linked journals first with `reverse-journal`. Invoice withdrawal preserves history and requires corrected reimport of the same source. Recompute reports after corrections. `backup-workspace --output <new.zip>` creates a consistent local snapshot; `restore-workspace --archive <zip> --destination <new folder>` restores for inspection. Never restore over a live workspace.

## Show the review table in Codex

Open the current stage's existing review artifact before asking the user to decide. Preserve the producing skill's Excel or HTML format; never replace its workbook with a CSV/HTML review. Route to the producing skill to create it if needed. Show one current review file at a time; do not open every historical export or unrelated period.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/reports/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Pass the period so invoice rows get a **Not for this BAS** button (the user's way to leave out private, duplicate or zero-amount documents; it is saved straight to the books and can be put back). Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review" --start <period start> --end <period end>` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.

## Document completeness and accrual workflow

After extraction, review every document independently of payment. For accrual GST, recognise bills and sales/RCTIs before or alongside matching; a missing payment does not exclude an unpaid invoice. Run workflow-status and inspect its documents list: recognised, deferred, excluded, unresolved or pending_gst. Opening a document is not recognition.

Use `review-document --request <JSON>` for period-specific decisions: invoice_id, start, end, status (excluded/deferred/unresolved), reason and, for deferred, review_after after the period end. Recognition derives from live journals. Retain source/payment timing and prior-claim evidence; never exclude documents merely to clear blockers. Source corrections invalidate decisions through their source hash. Deferred decisions apply only to that period and require review in later periods.

Route: setup and source inventory; import purchases, sales/RCTIs and all bank/card accounts; review document recognition, allocation and GST; match settlements without duplicate expenses/revenue; reconcile; resolve document/account/PAYG exceptions; prepare draft BAS. Cash and accrual have different timing; these are iterative passes rather than mandatory payment-first steps. Read classify-transactions references/accrual-workflow.md for entries.

## Identify the BAS work required

Reuse saved period applicability. Route missing or stale applicability facts to `tax-intake`; it owns the period interview and persistence. Validate its saved results before reporting readiness; do not repeat the interview here.

## Fixed HTML report contract

Use the bundled `review-table` renderer for every CSV review. Its fixed HTML
and controls live in `scripts/review_table.py` (canonical package source:
`accounting_core/review_table.py`). Do not generate a replacement HTML page,
invent a dashboard, rewrite CSS, or change layout between runs. Preserve the
renderer’s column order from the exported CSV, controls, labels, formatting,
source links and correction-request behaviour. Data, title, period, row counts,
issue messages and schema-required columns may change; presentation must not.
A different export schema may have different columns without a new design.

Open and verify the returned browser URL. Keep detailed results in that report;
chat should provide its link and any necessary action/blocker, not a duplicate
table. If the renderer fails, report the failure and link the saved CSV as an
explicit fallback; do not improvise another HTML design. Template changes require
an explicit implementation request and belong in the canonical source, followed
by release generation to synchronise bundled copies, never in per-run output.

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
