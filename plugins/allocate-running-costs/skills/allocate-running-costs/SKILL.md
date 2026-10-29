---
name: allocate-running-costs
description: Calculate the business portion of electricity, internet and phone costs; assess ATO actual-cost and fixed-rate methods using bills, usage and hours evidence. Use for home-office running costs, utility allocations and method comparisons.
---

# Allocate running costs

## Official guidance for tax and regulatory decisions

Read `references/official-sources.md` when this task requires tax or regulatory interpretation. Use live official guidance, cite exact sources and access dates, and report access failures explicitly. Routine extraction/matching does not establish GST or deduction eligibility.

Help calculate the business portion of running costs, considering both actual costs and the applicable ATO fixed-rate method. Produce a traceable calculation from bills, hours and usage evidence. Keep payment matching independent: a full bill can match a full payment even when only part relates to business. Read `references/user-workflow.md` for the user journey and expected report, `references/fixed-rate-request.md` when saving a fixed-rate calculation, and `references/ato-guidance.md` for the relevant rules and refresh linked ATO guidance for the applicable period before final tax treatment.

## Establish context

Reuse answers already provided. Ask only missing inputs, grouped into concise questions:

- Entity/business ID, company versus sole trader, reporting period, GST registration and cash/accrual GST basis.
- Bill recipient, actual payer, company payment/reimbursement evidence and date, and whether the same cost is included in another personal/business claim.
- Actual utility service dates, amounts, printed GST and tariff(s), plus source documents. A payment receipt is not a substitute for the underlying utility bill.
- Business-use records: home-working hours, electricity usage for equipment, lighting and heating/cooling, relevant equipment input or metered consumption, shared-space/private use; for phone/internet, a representative usage record and the method for calculating business share.

Pending answers do not prevent a draft calculation. They do prevent treating the result as an eligible BAS credit. Being a sole director/worker is not evidence of 100% business use. Confirm whose return the proposed deduction belongs to; avoid double claims for reimbursements or expenses covered by an income-tax fixed-rate method.

## Select and compare methods

Consider both methods before recommending one. Establish the claimant (individual, sole trader, company or trust), income year, who incurred each expense, reimbursement arrangements and records available. A company paying only the business portion must not be described as paying the household private portion. Do not assume a personal income-tax method establishes a company's reimbursement or deduction entitlement.

- **Actual cost:** calculate supported electricity, phone and internet business costs separately, excluding private use. For home-business usage extrapolation, follow the applicable representative four-week diary requirements and exclude holidays/non-use. Actual operating hours for an appliance may differ from home-working hours.
- **ATO fixed rate:** for an eligible claimant, calculate recorded home-working hours multiplied by the verified rate for that income year. The rate covers electricity for lighting/heating/cooling/electronics, gas heating, internet, phone, stationery and computer consumables together. It is not an electricity-only tariff or business-use percentage. Do not add separate deductions for expenses already covered, including phone use away from home. Separately eligible asset depreciation is outside this bundle.
- Verify the official rate and its applicable income years; save the source URL, access date and income year with the calculation. ATO guidance checked 15 October 2026 displays 70 cents/hour and says rates are reviewed yearly. This is not verification of a 2026–27 rate. Never extrapolate a prior-year rate into an unverified year or use the expired 52/80-cent methods for current periods.
- Fixed-rate evidence requires actual home-working hours across the entire income year, plus evidence for each covered expense actually incurred. Do not substitute a representative four-week hours diary for the full-year hours requirement. A quarter calculation is an interim subtotal, not proof of full-year eligibility.
- Show a comparison only on the same claimant, period and covered expense scope. Show methods as eligible, pending evidence or inapplicable with reasons; do not choose purely by the larger amount. For a company reimbursement, verify the company's specific treatment; keep an individual's fixed-rate comparison separate and avoid duplicate claims for reimbursed expenses.
- Never derive a BAS GST credit by dividing a fixed-rate deduction by eleven. Assess actual source expenses and GST entitlement separately.

Save fixed-rate calculations through `calculate-fixed-running-costs --request <JSON>`; list/export them with `running-cost-workpapers --business <ID> [--output <new CSV>]`. See `references/fixed-rate-request.md`. These are immutable SQLite workpapers with managed evidence and versioned corrections, independent of invoice allocations and journals. Never encode a fixed-rate result as `weekly_estimate`, fabricate an invoice, treat the bundled rate as an electricity reimbursement, or post it to BAS.

For personal fixed-rate eligibility distinguish paying initially from ultimately bearing an expense: fully reimbursed categories do not establish an unreimbursed additional expense. Some reimbursed categories do not automatically disqualify a claimant who still incurs other eligible additional running expenses; PCG 2023/1 paragraphs 49–50 apply. Ask about stationery/consumables as well as utility bills. Do not subtract reimbursement dollars from the hourly rate using an invented formula. Record payer, reimbursement outcome and supporting evidence for each category.

## Calculate electricity

Use the actual-cost method when requested. Calculate evidenced business energy for lighting, equipment and heating/cooling separately, then reconcile to the source usage charges.

For each usage/tariff segment:

`cost = electrical_input_kW × actual_operating_hours × price_per_kWh × justified_shared_use_factor`

- Prefer metered attributable energy where available: `business_kWh × tariff`.
- Electrical input is not cooling/heating capacity; indoor-unit wattage alone omits the outdoor compressor. Rated inverter input produces an estimate unless its use as representative consumption is supported.
- Work hours are not automatically AC operating hours. Split heating/cooling and tariff periods, exclude leave/non-use, and account for shared users.
- Apply an area/shared-use factor only where justified by how the appliance serves the space. Do not automatically apply an office-area percentage to every appliance or the entire household bill. Avoid applying the same adjustment twice.
- A billed controlled-load rate belongs only to the associated circuit. Use the correct general tariff for ordinary equipment; do not use an old tariff across a later quarter without evidence.
- Keep supply charges separate; do not include them automatically in a usage-based estimate. Discount/rebate adjustments require source-supported treatment; flag unresolved credits.
- Never allocate more than the relevant invoiced costs. Reconcile any discrepancy; do not silently cap an inconsistent calculation.

Record amounts and rates with decimal arithmetic; retain precision through intermediate steps and round final AUD amounts to cents. Distinguish GST-inclusive and exclusive inputs. No tax claim is derived solely from a rounded weekly estimate.

## Calculate internet and phone

Use the business share supported by relevant usage evidence, including other household users. For an ordinary uniformly priced mixed-use bill:

`allocated_cost = relevant_bill_cost × evidenced_business_share`

Document the measurement basis (business calls/data/time or another supported measure), representative period, family/private share and excluded periods. Use itemised charges when usage is directly identifiable. An office-area factor or working-hours fraction is not automatically an internet/phone business-use percentage. Do not invent a standard percentage.

## Assess GST and income tax separately

Maintain four independent statuses: extraction, payment matching, allocation evidence and GST eligibility.

- Retain printed GST as source evidence; unknown GST stays null. Do not mark missing GST as GST-free or invent one-eleventh merely because the supplier is Australian.
- With a supported uniformly taxable allocation, allocate source GST consistently to the eligible business portion. For an attributable GST-inclusive taxable energy cost, use one-eleventh only after establishing that treatment from valid source evidence. Mixed-tax/credit items require item-level treatment.
- Establish GST registration, acquisition/reimbursement entitlement and tax-invoice evidence. Personal payment alone does not establish a company GST credit. A director reimbursement needs evidence and its own timing assessment.
- Apply the confirmed cash/accrual basis and reimbursement rules to attribution; do not use service dates alone as BAS dates. If timing or entitlement is unresolved, leave the BAS amount pending.
- For income tax, identify the correct entity and supported business cost separately. Where entitled to an input tax credit, exclude that credit from the deduction. Not claiming a credit yet does not prove GST is deductible.

For uncertain claims, retain the gross allocated cost and evidence, with `gst_credit_cents: null` and a reason. Do not block payment matching merely because GST is unresolved.

## Save and report

Ask for or reuse the user's accounting workspace; use the selected accounting workspace consistently. For exports use `output/YYYY-MM-DD/` beneath that workspace, using the user's local date. Never overwrite an existing result; choose a new filename.

Store a JSON allocation record and a readable CSV/report with: business ID, invoice/source IDs, service/report periods, actual inputs and units, allocation method and factor, amount/tax basis, allocated cost, private balance where computable, reimbursement/payment evidence, GST amount/status, income-tax entity/status, unresolved issues, ATO links and calculation date. Record each bill once; aggregate without duplicating invoice/payment/reimbursement amounts.

## Persistent workflow

Use the bundled helper `scripts/accounting_store.py`, resolved relative to this skill directory. Reuse the same database location and business ID as the imported invoices; honour `AI_ACCOUNTING_DB`. Do not create a parallel database for an existing workflow.

1. Read saved rules: `python3 <helper> allocation-rules --business "<ID>"`. Prefer stored rules to asking the user again. The store creates schema version 5 automatically on the first write, preserving bank/invoice/payment records.
2. For a new or changed user instruction, write a rule JSON and run `save-allocation-rule --rule <JSON>`. Rule versions are append-only; retain provenance/evidence and effective dates. Never silently promote `user_stated` or `provisional` to `supported`. Overlapping date changes require separate allocation segments. Example percentage rule:

```json
{"business_id":"<ID>","supplier_key":"example-mobile-provider","category":"mobile","method":"percentage","business_percent":"<supported percentage>","effective_from":"2026-07-01","effective_to":null,"evidence_status":"user_stated","provenance":"User confirmed the stated business percentage; company pays bills; usage evidence pending"}
```

An electricity estimate uses `supplier_key: example-energy-provider`, `category: electricity`, `method: weekly_estimate`, `weekly_amount: "<supported weekly amount>"`, `evidence_status: provisional` and its supporting assumptions in `provenance`. The amount is the already allocated business cost: do not apply the same business-use adjustment again. These are user-specific examples, not default rules shipped to every user. Save them only when authorised in the conversation.

3. Retrieve the source invoices using `invoices --business <ID>`. Calculate and persist with `allocate-running-costs --request <JSON>`:

```json
{"business_id":"<ID>","supplier_key":"example-mobile-provider","category":"mobile","invoice_id":5,"period_start":"2026-07-01","period_end":"2026-09-30"}
```

The helper takes invoice amounts and GST from storage; request values cannot override them. Missing currency/source review permits a draft, not an eligible GST credit. Rules match the documented supplier, not filenames. Percentage allocations cover the full relevant invoice once; do not create duplicate period allocations for that invoice. Reverse an allocation using `correct-record` with kind allocation, id and reason before replacement. Reverse dependent journals first; history is retained.

For a weekly estimate, omit `invoice_id` when no valid source invoice is available and provide `active_weeks` excluding leave/non-use (if omitted, calendar weeks are used and must remain provisional). Estimates without source invoices have no computed private remainder or GST claim. An invoice-linked estimate may not exceed its amount; do not link a whole-quarter estimate to one shorter bill.

For `electricity_actual`, save an electricity rule with that method and submit `segments`: each needs `appliance_id`, `start`, `end`, `rate_per_kwh`, `business_percent`, `evidence`, and either (`input_kw` and `hours`) or `metered_kwh`, never both. Metered kWh represents the identified appliance/circuit consumption before any stated shared-use factor; use 100% only when that energy is already solely business use. Inputs are GST-inclusive; heating/cooling/changed tariffs for one appliance use non-overlapping dated segments. Set `usage_supported` only after source verification. Claim candidates require `uniform_gst_taxable` and printed source GST; unknown tax remains unknown.

4. GST stays pending by default. To assess eligibility, provide a `gst_eligibility` object only when verified: `gst_registered`, `company_acquisition_verified`, `tax_invoice_verified`, `business_use_verified`, `uniform_tax_verified` (all true), `basis` (cash/accrual), `attribution_date`, and `evidence`. The allocation rule must be supported and invoice verified in AUD. Cash-basis credits are limited to confirmed payment allocations in the reporting period. Reimbursement-only cases need separate verified attribution and must not be fabricated as invoice payments. Later tax review uses the audited correction/replacement workflow; do not bypass conflicts by changing dates/IDs.

5. Read `allocations --business <ID>` for results. Export with `allocations --business <ID> --output <workspace>/output/<local-date>/running-costs.csv`, creating the dated folder first. The CSV stores integer cents with explicit column names; present dollars in chat. Existing files are not overwritten. The output includes rule IDs, calculation inputs, business/private amounts, candidate/eligible GST, status and issues. SQLite retains immutable request/result snapshots and rule versions.


Print in chat: bill amount, supported business allocation, method, GST status, remaining questions and saved file locations. Do not submit BAS or change tax returns as part of this skill.

## Shared runtime

Use the Python executable at `<suite>/.venv/bin/python` when installed, otherwise the host Python 3.11+ runtime. Source files are copied into the workspace documents directory and hash verified. Relative evidence paths survive moving the complete workspace. The canonical runtime is maintained once in `accounting_core/` and bundled automatically for standalone plugins.

## Show the review table in Codex

Open the exported running-costs CSV before asking the user to review business amounts and GST status. When a fixed-rate comparison exists, open its workpaper CSV at that step, clearly distinguishing it from invoice allocations. Explain cents columns in dollars in the chat summary.

Save the review artifact under the selected workspace's `output/YYYY-MM-DD/` using the user's local date, choosing a new filename rather than overwriting an existing result. Use the helper's exported file where available. For a derived review CSV, use a CSV writer and faithfully preserve the returned records, stable IDs, null/unknown values, period, currency and amount units; do not invent data or change the accounting result to produce a table.

Show the CSV through the local table view by default. Start `python3 <helper> --db <selected workspace>/db/accounting.db review-table --csv <absolute CSV path> --title "<stage> review"` in a persistent command session. Read the initial JSON review_url, then call `open_in_codex` with `target: { type: "browser", url: "<returned review_url>" }` and `placement: "right"`. Reuse a current tab/server for the same unchanged CSV; stop stale servers when replacing them. The table provides search, sorting, issue filtering, formatted amounts/dates, managed-source document links and check/correction request buttons. Keep the underlying CSV as the versioned export. Do not open raw CSV text unless requested or the table cannot run; report a fallback honestly. If the tool returns queued, describe opening as queued rather than displayed.

The table saves requests under output/YYYY-MM-DD/review-request-*.json. It does not approve matches/classifications or update accounting records. When the user asks to process requests, read those for the current CSV, verify csv_sha256, row identity, original values and source evidence, then apply supported changes through the existing audited correction/import commands. Treat proposed values as user input, not verified facts. Ask only about unresolved evidence; preserve existing confirmation requirements for new accounting entries. Report applied versus pending requests explicitly and regenerate the affected CSV/table after corrections. An unchanged or stale CSV must never silently approve a request.

Opening or editing a review CSV does not confirm matches, approve classifications or update SQLite. Preserve the skill's existing confirmation requirements. If the user requests applying CSV edits, validate the changes against source evidence and use the existing audited correction/import commands; never silently replace database records from an edited export.
