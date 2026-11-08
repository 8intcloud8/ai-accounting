# Shared ATO research integration

Acceptance criteria recorded before validation:
- All 16 other package skills route tax/GST interpretation to installed ato-docs.
- Routine non-tax work does not trigger research; standalone fallback remains available.
- Reinstall each changed plugin and verify its skill matches canonical source.
- Fresh live invocation of representative BAS, allocation and tax-report entrypoints discovers shared research, fetches ATO evidence and cites applicable guidance without writing accounting records.

Changed plugins: allocate-running-costs, classify-transactions, extract-bankstatements, extract-invoices, grill-me-tax, manage-accounting, match-payments, prepare-bas, prepare-tax-report, reconcile-accounts, review-invoices, save-invoices, search-email-invoices, setup-accounting, setup-xero-mcp, upload-invoices-drive

## Static and installation evidence — 8 November 2026

Package build: 17 plugins; all 17 skill schemas valid. All 16 consuming skill entrypoints contain the shared research instruction and standalone fallback. Native Codex installation succeeded; each installed entrypoint matches canonical source. Alternate bill-search skill entrypoint also synchronized.

Installed versions:

- allocate-running-costs: 1.2.2
- ato-docs: 0.1.0
- classify-transactions: 0.1.2
- extract-bankstatements: 1.3.2
- extract-invoices: 1.1.2
- grill-me-tax: 0.1.1
- manage-accounting: 0.1.2
- match-payments: 1.1.2
- prepare-bas: 0.1.2
- prepare-tax-report: 0.1.2
- reconcile-accounts: 0.1.2
- review-invoices: 0.2.4
- save-invoices: 1.0.3
- search-email-invoices: 0.6.3
- setup-accounting: 0.1.2
- setup-xero-mcp: 0.3.2
- upload-invoices-drive: 0.1.2

## Live integration evidence

PASS: fresh read-only Codex run loaded installed prepare-bas 0.1.2, allocate-running-costs 1.2.2 and prepare-tax-report 0.1.2, then discovered/read ato-docs 0.1.0. It searched official sources, fetched GST legislation, ATO 2025 tax-return instructions and company home-business guidance; returned year/entity-specific conclusions with citations. No accounting commands or record changes occurred.

PASS: unavailable-source disclosure occurred: PCG 2023/1 access returned 403 and browser access was unavailable; response explicitly identified that source as not freshly verified. This does not validate that ruling's contents.

Coverage: representative tax consumers exercised together. Remaining 13 skills have source/install verification; their complete operational workflows were not rerun because this change only adds shared tax-research routing. Full tax accuracy across topics remains unevaluated.

### Observed response

**October payment does not necessarily move the GST credit.** Using your stated **non-cash basis**, the general rule attributes the credit to the earlier period of invoice issuance or any payment. A September invoice paid in October can therefore belong in July–September 2026. You generally must hold the required tax invoice when lodging that BAS; otherwise attribution is deferred, subject to exceptions. Entitlement and business use must also qualify. [GST Act, s29-10](https://www.legislation.gov.au/C2004A00446/2026-01-01/2026-01-01/text/original/pdf/1).

**For your 2024–25 employee return, no deduction for fully reimbursed expenses.** If your employer reimbursed **all** additional running expenses, the fixed-rate method is also unavailable. If only some categories were reimbursed, other unreimbursed eligible costs may still support fixed-rate eligibility; reimbursement alone does not automatically exclude it. The verified 2024–25 rate is **70c/hour**, subject to eligibility and records. [ATO 2025 instructions, D5](https://www.ato.gov.au/api/public/content/0-13e18f54-38a8-447a-84ce-4f830352fdfd); [PCG 2023/1, paragraphs 49–50](https://www.ato.gov.au/law/view/document?DocID=COG/PCG20231/NAT/ATO/00001).

Applying the requested skills:

- **prepare-bas:** assess invoice/payment attribution and tax-invoice evidence separately; October payment alone does not exclude September.
- **allocate-running-costs:** distinguish business/private allocation from who ultimately bears each expense. Exclude fully reimbursed costs from personal actual-cost deductions. Never derive company GST from the hourly rate.
- **prepare-tax-report:** keep the employee return and company workpaper separate; prevent duplicate deductions. Assess company reimbursement deductibility and GST entitlement independently.

Checked **8 November 2026**. GST legislation and ATO 2025 instructions retrieved; **PCG reimbursement guidance could not be freshly verified** because ATO returned 403 and browser access was disabled.

No reports created or records changed.

