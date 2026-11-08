# Accounting skill overlap audit

Reviewed 8 November 2026. Scope: all 17 package SKILL.md entrypoints, referenced policy/intake files, build bundling and selected alternate installed entrypoints. Source audit only: no live accounting workflows executed; no skills changed or data modified.

## Findings

### 1. High: orchestration omits intake and document review

`manage-accounting/SKILL.md` routes setup directly into collection/extraction; neither `grill-me-tax` nor `review-invoices` appears in its routing. Its later accrual workflow repeats a second route. A broad BAS request therefore lacks an explicit handoff to the intake and document-cleanup skills described in the intended process.

Recommendation: maintain one orchestrator route. Start/resume the period, read saved intake, route only missing intake to grill-me-tax, then collection, optional document housekeeping, imports, allocation/classification, matching/settlements, reconciliation and reporting. A user requesting a direct import need not be forced through optional cleanup.

### 2. Medium: intake and BAS applicability have several owners

`setup-accounting` collects entity/GST settings and reporting scope. `grill-me-tax` collects the same facts plus period obligations. The identical BAS applicability run/show/save paragraph appears in setup-accounting, manage-accounting and prepare-bas. Grill-me-tax points back to setup for persistence. Reusing facts is instructed, but there is no clear single owner of the period interview, making repeated questions/reports possible.

Recommendation: setup owns workspace/profile persistence; grill-me-tax owns the period interview and applicability answers using existing commands; manage-accounting routes and tracks; prepare-bas validates current saved applicability and requests a targeted refresh only when missing/stale. Preserve standalone entrypoints by routing to the owner rather than repeating a full interview.

### 3. Medium: extraction and classification both own the transaction workbook

`extract-bankstatements` step 6a performs business/private review and its Excel section specifies category, use, percentage and GST controls. `classify-transactions` also specifies Summary/Review/Original transactions and category/use/GST review. These are successive stages of the same review, not two independently generated workbooks. Both say to preserve earlier work, but the creation and refresh procedures are duplicated.

Recommendation: extraction owns faithful statement import, source identities and initial review artifact. Classification owns enrichment, corrections and posting from that same artifact; running-costs supplies supported splits. Keep source arithmetic checks in extraction and final account coverage in reconciliation.

### 4. Medium: chat-output instructions conflict with report-only instructions

`extract-invoices` step 5 says to show fields in chat and step 8 requires a chat summary; its later fixed HTML contract says detailed results belong in the report with only a short chat handoff. `match-payments` step 3 requires printing a candidate table while its final contract prohibits a duplicate chat table. `allocate-running-costs` requires chat bill/allocation summaries despite its final report contract.

Recommendation: each skill has one presentation contract. Populate detail in its prescribed report; chat contains the report link, specific unresolved question or blocker. Preserve the explicitly chosen Excel format for bank/classification reviews.

### 5. Medium: tax research instructions are layered and partially conflicting

All 16 consumers now have the ato-docs hook. Fifteen also have a separate immediate ato-first read instruction; twelve have an additional official-guidance section. All 16 bundle identical ato-first and proactive-tax-review references. The shared hook was added without consolidating these older instructions. ato-docs says search first; ato-first says inspect records before tax-related recommendations/questions. A consumer may follow several overlapping research sequences.

Recommendation: define order explicitly: inspect known case facts, then use ato-docs for applicable law, then apply it. Keep transaction-specific accounting checks in the consumer. Retain a concise standalone fallback. Generate genuinely shared references from one maintained source; do not delete service-specific or regulatory guidance blindly. Official-sources files differ across consumers and require comparison before consolidation.

### 6. Medium: extraction owns expense-claim administration as well as import

`extract-invoices` records payment ownership, claim approval, unreimbursed confirmation and historical reimbursements through record-purchase. `match-payments` also links reimbursements with the same action. This is more than field extraction, although the matching text correctly distinguishes supplier payment from company reimbursement.

Recommendation: make one owner responsible for expense-claim state and define explicit handoffs. Matching should supply bank links; extraction should import invoice facts and display saved claim state. Preserve the distinction among evidence, claim approval, payment recording and journal posting. No existing skill currently owns the whole claims lifecycle cleanly.

### 7. Low: alternate installed entrypoints remain

The direct bill-search search-email-invoices entrypoint and ai-accounting 0.6.3 entrypoint both exist and currently match. A claude-cowork setup-xero-mcp 0.3.0 entrypoint also exists and differs from the package version. File existence alone does not establish whether the older plugin is enabled; do not delete caches without checking registrations and dependencies.

Recommendation: select one installed source per skill name, verify registrations, and retire redundant aliases through supported uninstall/discovery configuration when safe.

## Responsibility map

| Skill | Intended owner responsibility |
|---|---|
| manage-accounting | Guide the process, resume saved state, route and track blockers |
| setup-accounting | Create/select workspace and persist business profile/configuration |
| grill-me-tax | Collect missing case facts and period/year evidence requirements |
| ato-docs | Research official tax guidance and return cited conclusions |
| search-email-invoices | Discover email candidates and present selection checklist |
| save-invoices | Download selected candidates and preserve manifest |
| upload-invoices-drive | Store selected originals in the bound Drive invoice space |
| review-invoices | Review source-document quality/duplicates and approved quarantine |
| extract-invoices | Import invoice facts and preserve source evidence |
| extract-bankstatements | Import complete validated statement transactions |
| allocate-running-costs | Calculate supported running-cost splits and comparisons |
| classify-transactions | Own accounting treatment review and confirmed journal posting |
| match-payments | Link bank movements and invoices/claims without duplicate recognition |
| reconcile-accounts | Verify independent statement balances, coverage and unresolved differences |
| prepare-bas | Validate readiness and produce the supported GST draft |
| prepare-tax-report | Produce annual bookkeeping/tax-review workpapers |
| setup-xero-mcp | Optional Xero connection setup and repair |

## Duplication that is justified

- All 17 canonical entrypoints have distinct names; no exact duplicate skill entrypoint was identified in the package.
- Search versus save, document review versus extraction, allocation versus classification, payment links versus postings, and reconciliation versus reporting have distinct outputs. Keep them separate.
- Runtime copies under plugin scripts are intentionally generated from accounting_core for standalone installation. Do not manually remove them; maintain canonical modules and rebuild.
- A shared renderer/style is desirable. Different report datasets are not duplicate accounting work. Source import arithmetic does not replace independently evidenced account reconciliation.

This audit identifies instruction-level risks, not proof that duplicate postings or repeated questions have occurred in a particular run. No skill refactor, installation change or full workflow validation is included in this report.
