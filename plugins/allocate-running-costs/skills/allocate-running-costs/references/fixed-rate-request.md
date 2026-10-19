# Saving fixed-rate workpapers

Use the same helper and selected workspace as all accounting skills:

```sh
python3 scripts/accounting_store.py calculate-fixed-running-costs --request <request.json>
python3 scripts/accounting_store.py running-cost-workpapers --business <business-id> --output <workspace>/output/<local-date>/fixed-rate-workpapers.csv
```

Paths above are relative to the skill. Create the dated output folder first; exports refuse to overwrite files. Save the complete returned JSON as a new review artifact as well. All monetary output columns explicitly use integer cents.

## Request fields

- `business_id`: configured workspace owner. `claimant_id`: stable identity of the person whose deduction is considered; do not equate company ID and director identity. `claimant_type`: individual, sole_trader, company, trust or partnership. Company/trust/partnership requests return inapplicable for this individual's fixed-rate calculator; they require their own treatment.
- `period_start`, `period_end`: ISO dates within one Australian income year, 2023–24 onwards.
- `hours`: list of `{ "date": "YYYY-MM-DD", "hours": "7.5" }`. Consolidate each date once; each day must be between 0 and 24 hours. List actual home-working days. No fabricated hours or extrapolated year.
- `hours_evidence_file`: actual diary/timesheet source path. `actual_hours_verified`, `full_year_hours_complete`, `work_from_home_for_income_verified`, `expense_evidence_verified`: set true only after evidence checks. A partial-year period remains pending for annual readiness regardless of these flags.
- `fixed_rate`: null when unknown. Otherwise contains `aud_per_hour` (decimal AUD, not cents), `income_year_start`, `income_year_end`, official HTTPS ATO `source_url`, ISO `checked_on`, `verification_note` describing evidence tying rate to this year, and `verified_for_income_year`. False/unverified yields no calculated deduction; a mismatched year is rejected. The URL and flags preserve the assistant's checked evidence; they do not fetch or authenticate legal content automatically. Do not hardcode a rate for future years.
- `expenses`: object with all keys `electricity`, `gas`, `internet`, `phone`, `stationery`, `computer_consumables`. Each has `payer` (claimant, third_party, not_incurred or unknown) and `explanation`. Claimant-paid categories also require `evidence_file`, `reimbursement` (none, partial, full or unknown) and `unreimbursed_additional_cost_verified`. The last flag is true only where an eligible additional expense remains after reimbursement and evidence review. Use `third_party` for company-incurred business costs. Optional evidence files on other categories are also retained.
- Corrections: `supersedes_ids` lists every current overlapping workpaper for the same claimant; include `correction_reason`. A replacement must fully contain the replaced periods. This allows an annual calculation to replace multiple quarterly workpapers. `supersedes_id` is accepted for one previous version. Do not supply both forms. Historical entries remain visible and are marked superseded, with no current review-ready amount.

## Output interpretation

`calculated_cents` is arithmetic only when a year-specific rate is verified and claimant is not inapplicable. `review_ready_deduction_cents` is present only when annual checks pass. `status` is pending, inapplicable, review_ready or superseded. No output is automatically a lodged claim. `gst_credit_cents` is always null. Saved source documents are copied under `documents/`; their hashes are rechecked when listing or replaying a saved result. Altered/missing evidence removes current readiness.

`running-cost-workpapers` exports all saved versions and a superseded flag. Never total historical and current entries together. Fixed workpapers are excluded from invoice allocations, journals and BAS totals. Use actual source expense allocations for company costs and GST.
