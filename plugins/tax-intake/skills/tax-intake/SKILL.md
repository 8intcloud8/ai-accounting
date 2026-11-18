---
name: tax-intake
description: Ask the missing questions and collect evidence needed before Australian BAS or income-tax-return preparation. Use for initial intake or changes in a returning client's circumstances.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

## Shared ATO research

Inspect available case facts first. Before interpreting Australian tax or GST rules, use the installed `ato-docs` skill: discover and read its `SKILL.md`, then follow its official-source search, page retrieval, entity/year checks and citation workflow. Carry the conclusion, source URLs/sections, access date and unresolved facts into this skill's work. Routine searching, saving, extraction, matching and technical setup require no tax lookup unless tax treatment is being assessed.

If `ato-docs` is unavailable, read references/ato-first.md and follow this skill's bundled official-source guidance and disclose the fallback when giving tax conclusions. Do not block routine work or claim that shared research ran when it did not. Tax research does not approve accounting entries or lodgment.

Draft intake coverage. This questionnaire has not yet been mapped exhaustively to year-specific BAS and return instructions or independently reviewed. Record uncovered topics as unresolved.

Read references/ato-first.md and references/intake-topics.md. Research current official ATO guidance for the relevant entity and reporting year before assessing treatment. This skill prepares an intake and evidence plan.

## Start with available facts

Read the selected workspace profile, previous intake, reporting settings and supplied records. Identify what is known, its source and applicable dates. Reuse confirmed facts for their applicable entity and period. Verify changes when a new period could affect them. Keep the company and its director's individual return as separate cases. A sole trader's business belongs in their individual case.

Ask which work is wanted (BAS, tax return or both), for whom, and which dates only when missing. Establish original versus amendment, business structure and activities, start/stop or ownership changes, and any relevant residency changes. Resolve the workspace through setup-accounting if needed. Do not request full TFNs, account credentials or refund banking details for intake.

## Interview progressively

Use the topic reference as a coverage checklist. Ask at most three related questions per turn, with ordinary language and an unknown option. Explain briefly why a question matters when it is unclear. Ask about events and records, then assess applicable law yourself. Do not ask the user to diagnose PSI, Division 7A, GST-free status or deduction entitlement.

First screen for applicable topics. Drill down only into triggered branches. Inspect already-authorised records before asking the user to repeat information. Never ask the user for an amount or total the records can produce (e.g. wages paid, loan repayments, sales): compute it from the bank transactions and documents, show the figure and workings, and ask only for confirmation or the specific missing document. A missing or blank answer stays unknown. Record explicit negative answers. New transaction evidence can reopen an apparently inapplicable topic.

For BAS, obtain the actual activity statement obligations, frequency, GST registration effective dates and cash/non-cash basis. Own the period-specific applicability interview: use setup-accounting's bundled accounting_store.py helper to run bas-applicability for the selected start/end, then save confirmed answers with save-bas-applicability --request <JSON>. Read its references/bas-applicability.md for the schema. Reuse existing supported answers; only ask missing or stale facts. Route profile/configuration writes through setup-accounting. If that helper is unavailable, retain the intake and report persistence as pending. Registration alone does not establish Simpler BAS scope. GST basis does not determine income-tax accounting treatment.

For annual returns, use the entity-specific branch and reporting-year instructions. Establish the income sources, evidence and year-end adjustments needed. Check claimed/reimbursed costs across company and personal cases to avoid duplicate claims. Store business-use facts separately from GST and income-tax decisions.

## Save and continue

Save an intake JSON and concise Markdown evidence checklist under the selected workspace's output/<local-date>/reports/tax-intake-<unique-run-id>/. Once a run has started, update its own artifacts and preserve previous answers with a dated change history. Each case records entity, task, dates, question ID, answer, unknown/confirmed/evidence-pending status, source, confirmed date, effective period, linked evidence and next action. Collect only data needed for applicable questions. Never put private client answers in the package source or global agent memory.

End each interview session with known scope, unanswered facts, missing records, applicable specialist follow-ups and saved paths. Intake completeness means applicable questions have supported answers or explicit unresolved items. It never establishes tax calculation or lodgement readiness.

Route source collection to search-email-invoices, extract-bankstatements and extract-invoices; running-cost evidence to allocate-running-costs; ongoing work to manage-accounting; GST workpapers to prepare-bas; annual bookkeeping workpapers to prepare-tax-report. Flag calculations or schedules unsupported by those tools for specialist review. Continue independent supported work while missing evidence is outstanding.

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

