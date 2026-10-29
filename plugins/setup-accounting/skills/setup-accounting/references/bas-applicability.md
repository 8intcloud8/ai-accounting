# BAS applicability review

Use this when preparing a BAS period. It identifies required work; it does not calculate tax or complete the annual return. Read the saved profile, source inventory, period records and previously confirmed answers first. Confirm actual ATO activity-statement obligations rather than deriving them from GST registration or the absence of bank payments.

1. Run `<helper> --db <workspace>/db/accounting.db bas-applicability --start YYYY-MM-DD --end YYYY-MM-DD`. It saves a versioned CSV and returns each question, current answer, evidence and follow-up action. Open saved_csv using review-table in the Codex browser panel.
2. Ask missing questions in small meaningful groups: applicable ATO obligations, exceptional transactions, then supporting records. Reuse facts already explicitly confirmed for this business and period. Do not ask sixteen unrelated questions at once. A statement showing which sections apply can support several answers together; read it first.
3. Save only answered topics through `save-bas-applicability --request <JSON>`. Payload: business_id, start, end, answers. Each answer includes topic, answer (yes/no/unknown), evidence (actual source or user confirmation) and provenance (user_confirmed/source_verified/unknown). A definite answer needs confirmed provenance. No transaction found is not proof of no obligation. Never mass-fill no to clear blockers.
4. Obligation topics: payg_withholding, payg_instalments, fbt_instalments, wine_tax, luxury_car_tax, fuel_tax_credits, deferred_import_gst. Event topics: vehicle_events, capital_events, overseas_purchases, insurance_events, finance_agreements, owner_loans, grants, payroll_terminations, cash_activity.
5. Explain results: no means no task identified from that confirmed answer; unknown requires an answer; yes creates a specific review task and owning skill. Applicable additional tax calculations remain outside this version's GST-only engine and block readiness. Transaction-event reviews can be completed using the evidence-backed workflow below. Additional BAS obligation calculations remain unsupported and cannot be cleared with this command. A saved yes, generic checkpoint or correction request is not completed work.
6. Imported period evidence/profile/scope changes make existing answers stale. Recheck the saved answers against new evidence; reuse their context and ask only unresolved questions. Another reporting period starts with unanswered scope questions. Answers are append-only and corrections retain history.
7. Regenerate/export after saving answers and show the updated table plus a short pending list. Assessment complete means all answers known/current; follow-up tasks may still block BAS preparation. Never equate it to ready for lodgement.

Example for a user-confirmed fact only:

```json
{"business_id":"example","start":"2026-07-01","end":"2026-09-30","answers":[{"topic":"vehicle_events","answer":"no","evidence":"User confirmed no vehicle acquisitions/disposals/trade-ins in this period","provenance":"user_confirmed"}]}
```

Current references (checked 26 October 2026):
- https://business.gov.au/finance/tax/business-activity-statement — sections depend on registrations and reporting period.
- https://www.ato.gov.au/businesses-and-organisations/income-deductions-and-concessions/payg-instalments — notified amount/rate methods.
- https://smallbusiness.taxsuperandyou.gov.au/paying-workers/withholding-amounts — withholding evidence/reporting.
- https://www.ato.gov.au/api/public/content/0-5cfa3e60-d95b-41aa-9be1-cea62009de33 — deferred import GST context.

Refresh applicable tax guidance before final treatment. The accountant's checklist guides operational completeness; it does not establish entitlement or current rates.

## Complete a transaction-event review

Route to its owning skill, inspect actual documents and apply any necessary classifications, journals or reconciliations through existing audited helpers first. Resolve the specific next_action, explain the treatment and obtain explicit user confirmation of this completed review. Do not invent confirmation or a reviewer identity. A saved file is supporting evidence, not proof that accounting treatment is correct.

Call `complete-bas-task --request review.json` with business_id, start, end, topic, reviewer (actual person confirming review), conclusion (specific treatment, entries/reconciliations and rationale), confirmed: true, and evidence_files (1–30 paths inside this workspace). Preserve original source documents and save review workpapers under output/YYYY-MM-DD. Files must exist, be nonempty and at most 12 MB each. Prefer original source evidence plus the reviewed workpaper; do not create a placeholder solely to satisfy validation.

This supports the nine transaction-event topics only. A current yes answer is required. Completion is append-only, audited, bound to that exact answer, evidence hashes and accounting state. Editing/deleting evidence, changing entries/reconciliations or replacing the answer requires another review. Regenerate bas-applicability, open its saved CSV in review-table and show what remains blocked. Completed scope review clears only that scope blocker, never other accounting/GST checks. The seven additional BAS obligation calculations remain blocked pending implementation; never change an applicable answer to no to bypass them.

Example shape (replace with actual confirmed facts):
```json
{"business_id":"example","start":"2026-07-01","end":"2026-09-30","topic":"capital_events","reviewer":"Actual reviewer","conclusion":"Document the reviewed treatment and posted entry references","confirmed":true,"evidence_files":["documents/source.pdf","output/2026-10-26/capital-review.csv"]}
```
