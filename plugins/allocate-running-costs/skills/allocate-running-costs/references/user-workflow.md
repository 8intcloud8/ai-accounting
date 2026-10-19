# User workflow: calculate running costs

The user says: **“Calculate my business running costs for July to September. The company pays only the business portion.”** Or: **“Compare actual costs with the ATO fixed-rate method for my personal return.”** The assistant performs the calculations; the user does not edit JSON, administer SQLite or choose a tax rate from memory.

## 1. Select the task and period

Resolve the saved accounting workspace, business identity and reporting dates. Establish whether the output is a company business-cost/reimbursement calculation, a sole-trader/individual income-tax calculation, or both as separate workpapers. A BAS quarter and an income year are different scopes. Reuse confirmed facts, asking only missing questions.

## 2. Collect source evidence

Use stored bills or ask which folder holds electricity, internet and phone bills, plus hours/usage records. Read actual PDFs/images using the extraction skill as needed. Identify service dates, tariff periods, inclusive/exclusive GST basis, credits and printed GST. Reuse invoice IDs; avoid recording payments and invoices as separate expenses. Fixed-rate expense scope also includes gas heating, stationery and computer consumables; ask whether these were incurred.

## 3. Establish who bears each cost

Record whose bill it is, who paid initially, whether the business directly pays only its share or reimburses it, and the actual reimbursement outcome. Record personal amounts outside the company. For personal fixed-rate eligibility assess whether at least one eligible additional running expense remains unreimbursed. Some employer-paid costs do not automatically make that method unavailable. Confirm any other claims for the same costs.

## 4. Establish methods and records

**Actual cost:** get metered attributable consumption or equipment electrical input and operating hours, the supplier tariff, shared/private use and usage evidence. Include lighting and equipment as well as heating/cooling. For internet/phone use supported usage shares. Explain missing evidence and leave estimates provisional.

**Fixed rate:** verify claimant eligibility, the ATO rate for the precise income year, actual home-working hours recorded for the whole year and evidence of incurred covered expenses. A representative four-week diary cannot replace full-year hours records for this method. The revised calculator supports 2023–24 onwards; refer earlier transition years for separate review. If the current-year rate cannot be verified, save pending status without calculating a deduction. A quarter subtotal stays interim.

## 5. Calculate transparently

Show each actual-cost input and formula. Example only: 100 metered kWh × $0.35/kWh × 80% business use = $28.00 gross business electricity. Source bills and supported usage still determine eligibility.

For a verified eligible fixed-rate case, show actual recorded hours × the applicable rate. The result covers the bundled categories; it is not the electricity portion of a household invoice. Separately eligible depreciation belongs outside both running-cost comparison totals. Compare the same claimant, year and covered categories. Do not compare only actual electricity against the whole fixed-rate bundle, add company reimbursements to personal deductions, or select a method solely because it produces the larger number.

## 6. Assess GST separately

Use source invoice GST, the supported business allocation, company acquisition/reimbursement evidence and confirmed attribution basis. The fixed hourly rate has no calculable GST component. Do not turn a pending or non-applicable income-tax calculation into a BAS claim. Show unknown as unknown, rather than zero.

## 7. Present results for review

Print a concise table with method, claimant, period, business amount, GST status, evidence status and outstanding inputs. For fixed rate display calculated amount separately from review-ready annual deduction. Show inapplicable/pending reasons. Explain the proposed method and covered categories. A user confirmation does not replace source evidence. No automatic tax-return submission or BAS finalisation occurs.

## 8. Save and resume

Store actual allocations and fixed-rate workpapers separately in the same SQLite workspace. Copy supporting evidence into managed documents with hashes. Export review files under `output/YYYY-MM-DD/` using the user's local date, without overwriting. Give clickable output links. Save user-specific allocation rules only for that business, with effective dates and evidence status; refresh year-specific rates and usage support rather than blindly carrying everything forward. Corrections preserve previous versions. At year end consolidate interim fixed-rate records through explicit supersession, never sum them with the annual amount.

## What the user receives

- Business electricity/internet/phone breakdown with inputs and formulas.
- Eligible fixed-rate comparison, or a specific reason it is pending/inapplicable.
- GST assessment separately from income-tax/reimbursement amounts.
- Missing evidence/actions and saved CSV/JSON locations.
- Saved progress reusable next period, with year/rate/evidence checks.
