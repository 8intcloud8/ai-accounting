---
name: grill-me-tax
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

First screen for applicable topics. Drill down only into triggered branches. Inspect already-authorised records before asking the user to repeat information. A missing or blank answer stays unknown. Record explicit negative answers. New transaction evidence can reopen an apparently inapplicable topic.

For BAS, obtain the actual activity statement obligations, frequency, GST registration effective dates and cash/non-cash basis. Own the period-specific applicability interview: use setup-accounting's bundled accounting_store.py helper to run bas-applicability for the selected start/end, then save confirmed answers with save-bas-applicability --request <JSON>. Read its references/bas-applicability.md for the schema. Reuse existing supported answers; only ask missing or stale facts. Route profile/configuration writes through setup-accounting. If that helper is unavailable, retain the intake and report persistence as pending. Registration alone does not establish Simpler BAS scope. GST basis does not determine income-tax accounting treatment.

For annual returns, use the entity-specific branch and reporting-year instructions. Establish the income sources, evidence and year-end adjustments needed. Check claimed/reimbursed costs across company and personal cases to avoid duplicate claims. Store business-use facts separately from GST and income-tax decisions.

## Save and continue

Save an intake JSON and concise Markdown evidence checklist under the selected workspace's output/<local-date>/reports/grill-me-tax-<unique-run-id>/. Once a run has started, update its own artifacts and preserve previous answers with a dated change history. Each case records entity, task, dates, question ID, answer, unknown/confirmed/evidence-pending status, source, confirmed date, effective period, linked evidence and next action. Collect only data needed for applicable questions. Never put private client answers in the package source or global agent memory.

End each interview session with known scope, unanswered facts, missing records, applicable specialist follow-ups and saved paths. Intake completeness means applicable questions have supported answers or explicit unresolved items. It never establishes tax calculation or lodgement readiness.

Route source collection to search-email-invoices, extract-bankstatements and extract-invoices; running-cost evidence to allocate-running-costs; ongoing work to manage-accounting; GST workpapers to prepare-bas; annual bookkeeping workpapers to prepare-tax-report. Flag calculations or schedules unsupported by those tools for specialist review. Continue independent supported work while missing evidence is outstanding.
