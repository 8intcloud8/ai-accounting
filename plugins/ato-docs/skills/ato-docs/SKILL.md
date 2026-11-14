---
name: ato-docs
description: Research official Australian Taxation Office guidance for BAS, GST, income tax, deductions, recordkeeping and tax-return preparation. Use for tax interpretation and source verification alongside accounting skills.
---

## Shared case memory

When working in a selected accounting workspace, use manage-accounting’s `references/case-workflow.md` memory workflow to recall applicable entity/period facts before asking questions. Persist explicit new facts and corrections through its memory helper, read them back, and return evidence to the coordinator. Resolve conflicts with operational profile/allocation records through their owning skill; memory does not authorize posting or establish tax entitlement. If the coordinator is unavailable, disclose memory persistence as unavailable rather than claiming information was saved.

# ATO Docs

Provide current, cited ATO guidance applicable to the taxpayer and reporting period.

## ATO library first

ATO guides chosen by the plugin maintainers ship with the plugins (`ato-library/library.json` next to `scripts/`); the same library serves every workspace and needs no `--db`. Search it before the web: `scripts/accounting_store.py ato-search "<2-6 essential terms>" --period-end YYYY-MM-DD`. Plain words must all match; use `"exact phrase"` or `OR` for synonyms (e.g. `car OR "motor vehicle"`) and retry with other ATO wording before giving up. Results give guide, page, heading, a passage and warnings. Read the whole page with `ato-page --guide <sha256> --page <n>` before relying on it; `ato-guides` lists the library. Never run `ato-add` or `ato-sync`: they are maintainer commands for the codebase.

When answering from the library, show the source as a link to the guide itself, not the web page: `[<guide title>, p.<n>](<link>)` using the `link` field from `ato-search`/`ato-page` (it opens the PDF at that page), then the exact quoted sentence on its own line, then the ATO address as "Source: <url>". If `link` is empty, name the guide and page without a link. Do not fetch the web page just to confirm a library answer; check the web only when a warning says the guide may be out of date.

Cite a library guide as `{"library":{"sha256":"<guide sha256>","page":<n>,"quote":"<exact sentence from that page>"}}`. The code rejects a quote that is not on that page word for word, so copy it from `ato-page`. Treat a warning (older than 12 months, outside the guide's stated years, no ATO address) as a reason to check ato.gov.au for a current version; say so when you still rely on it.

If the library has nothing applicable, or the guide is stale, research the web as below and mention the page as a candidate for the library in your report.

## Web research

**First substantive action (when the library has no answer):** Search the exact requested ATO topic using a concise query of 2–6 essential terms. Use an available official ATO documentation search and page-retrieval capability first; otherwise search the web restricted to `ato.gov.au`. Actually open or fetch the relevant official page before answering. Search snippets, unopened links and prior answers do not establish the rule.

## Establish applicability

Use facts already supplied. Establish the relevant income year or BAS period, claimant/entity (individual, sole trader, company, trust or partnership), and facts material to the requested treatment. For GST, establish registration, cash/non-cash basis and relevant evidence where they affect the answer. Ask only for missing facts that change the conclusion; explain conditional outcomes when useful.

Read the page's eligibility, exclusions, evidence requirements and applicable dates. Follow relevant linked guidance when the first page does not establish the answer. A current page may describe a different income year: verify historical or future-year applicability explicitly. Never carry a rate, threshold or method into another year without supporting guidance.

## Source and interpretation boundaries

- Prefer `www.ato.gov.au` guidance and `www.ato.gov.au/law/` rulings and determinations. Use official ATO educational material on `taxsuperandyou.gov.au` only when useful, following the primary ATO guidance for the conclusion. Confirm official provenance before using another host.
- Distinguish ATO public guidance, public rulings, practical compliance guidance, draft material and community discussion. Do not present a draft, community response or educational example as a binding ruling. Check ruling status, amendments, withdrawal and date of effect when relevant. Private rulings for other taxpayers do not establish this taxpayer's entitlement.
- If statutory wording is needed, read the relevant version on `legislation.gov.au` and identify it as legislation. Report unresolved conflicts or interpretation rather than silently choosing a favourable result.
- Use general tax topics in searches; keep client identifiers, private documents and account details out of search queries.
- Separate income-tax deductions, GST credits, timing and business-use allocation. Check who incurred or reimbursed the expense. Do not transfer employee or sole-trader methods automatically to company claims, infer GST from an invoice total, or turn a deduction into a GST credit without evidence.
- Informal notes and summaries are not sources. The bundled ATO library holds the official guides themselves; anything else must be verified on the official site. No embeddings or API key are needed.

## Answer with evidence

Answer the actual question first. Cite the library page (guide, page, exact quote) or the fetched web page (exact URL, heading or ruling paragraph) supporting each material tax conclusion. Identify the applicable year/period and distinguish sourced rules from their application to the supplied facts. For calculations show inputs, units, rate source, business portion and result; keep unsupported inputs provisional.

State the specific missing fact or unavailable source when it prevents a conclusion. If a page is blocked, try another official page or official printable/PDF version. If still unavailable, disclose that verification failed; do not treat a snippet as verified guidance or guess a rate.

When another accounting skill uses this research, pass back the conclusion, applicable entity/period, supporting URLs and sections, access date, and unresolved evidence. Research alone does not authorize ledger changes or lodgment. Save a research report only when the user or calling workflow requests one, using its selected workspace and report location.
