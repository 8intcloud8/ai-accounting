# Official-source lookup in the accounting suite

Each of the 12 skills includes `references/official-sources.md` and a direct instruction to read it before tax or regulatory interpretation. References are packaged inside each skill so separately installed plugins do not depend on a sibling plugin or a developer's local directory.

## Behaviour

- Resolve the entity, issue and relevant reporting/income period.
- Search the applicable official domain and read the specific supporting page, ruling or provision. Topic links are discovery seeds, not an exhaustive knowledge base or preverified rules.
- Verify application dates, exceptions and current/withdrawn/draft status; use historical guidance when the transaction period requires it.
- Cite the exact URL, supporting heading/paragraph and access date beside material conclusions. Save the source record alongside the draft workpaper.
- Prefer applicable official guidance over saved educational summaries. Local GST course downloads are optional background, not the suite's knowledge boundary, and are not bundled by this change.
- Report missing browsing tools, 403/404 responses, timeouts and unavailable guidance explicitly. Open alternative official pages before relying on them; snippets are discovery only. Leave dependent treatment pending and continue unaffected draft work.
- Do not send client identifiers, invoice contents or financial records to a public search service. Use generic rule/entity/period terms.

The host supplies browsing/search tools. These instructions add no network service, crawler, background refresh job, tax engine or payroll capability. They preserve existing classification confirmation and evidence requirements. Routine discovery, document extraction, saving, arithmetic reconciliation and payment matching do not require browsing unless a rule is being interpreted.

## Topic routing

| Skill | Starting topics |
| --- | --- |
| setup-accounting | Registration, BAS, record keeping, employer obligations |
| manage-accounting | BAS, GST, deductions, records, PAYG, super, company/workplace records |
| extract-bankstatements | ATO business records and ASIC company records |
| extract-invoices | Invoice evidence, GST credits, business records |
| search-email-invoices / save-invoices | Document retention and invoice evidence; discovery/saving is not tax eligibility |
| match-payments | GST credits, cash attribution, payment evidence |
| reconcile-accounts | Source statement and company/business record requirements |
| classify-transactions | GST, deductions/capital costs, reimbursements, PAYG/super issues |
| allocate-running-costs | Actual/fixed-rate deductions, eligible claimant, reimbursements and separate GST credit tests |
| prepare-bas | BAS labels, GST, attribution, PAYG/super follow-ups, evidence |
| prepare-tax-report | Business deductions, assets/depreciation, GST separation, company/employer obligations |

Use ATO for tax and super, ASIC for company records and Fair Work for workplace records. Follow relevant official links or search for a topic not covered by the starting list. A reference to an obligation outside the current engine's scope identifies a separate review requirement; it does not certify that calculation as complete.

## Source-record example

Save as a new `official-sources-<unique-suffix>.json` under the selected workspace's dated output directory. This is a suggested document format, not a new database schema or command.

```json
{
  "issue": "GST attribution for a partly paid invoice",
  "entity_type": "company",
  "reporting_period": "2026-07-01 to 2026-09-30",
  "title": null,
  "url": "https://www.ato.gov.au/law/view/document?DocID=GST/GSTR200013/NAT/ATO/00001",
  "section_or_paragraph": null,
  "application_dates": null,
  "access_date": "2026-10-28",
  "status": "not_verified",
  "conclusion_or_limitation": "Example only: replace with the actual access result and applicability assessment."
}
```

Only mark a rule verified after reading supporting content and checking applicability. Record access failures with their actual cause. Do not infer an effective date from the access date or overwrite a saved good source with an error page.

## Source access checked during this change — 2026-10-28

| URL | Observed result |
| --- | --- |
| https://www.ato.gov.au/businesses-and-organisations/preparing-lodging-and-paying/business-activity-statements-bas | Browser fetch returned 403; content not verified |
| https://www.ato.gov.au/businesses-and-organisations/income-deductions-and-concessions/income-and-deductions-for-business/deductions | Browser fetch returned 403; content not verified |
| https://www.ato.gov.au/businesses-and-organisations/super-for-employers | Browser fetch returned 403; content not verified |
| https://www.ato.gov.au/businesses-and-organisations/preparing-lodging-and-paying/record-keeping-for-business | Browser fetch returned 403; content not verified |
| https://www.asic.gov.au/for-business-and-companies/companies/company-building-blocks/company-record-keeping | Page content retrieved |
| https://www.fairwork.gov.au/tools-and-resources/fact-sheets/rights-and-obligations/record-keeping-pay-slips | Page content retrieved |

Other starting links have not all been opened during this change. No client-specific legal conclusion is established by this access check. Runtime access may differ; retry at the relevant decision and keep the result honest.
