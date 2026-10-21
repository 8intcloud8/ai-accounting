# Accrual example: recognition followed by settlement

Use actual verified evidence and IDs, never these illustrative IDs. Obtain confirmation for new classifications. Dates below assume invoice issued first and ordinary non-cash attribution applies; check earlier consideration, tax-invoice holding, reimbursement and special rules independently. Invoice date, service period, journal date and GST attribution are separate concepts.

## Purchase AUD110 including GST10

Import role=purchase, verified source, invoice_id=1. Recognise when appropriate:

```json
{"reference":"purchase-recognition-1","date":"2026-07-01","description":"Supplier bill","invoice_ids":[1],"lines":[{"account":"5000","debit_cents":10000},{"account":"1200","debit_cents":1000},{"account":"2000","credit_cents":11000}],"gst":{"label":"purchase","gross_cents":11000,"gst_cents":1000,"status":"reviewed","attribution_date":"2026-07-01","evidence":"Verified company tax invoice and non-cash attribution"}}
```

Match the later AUD110 bank debit to invoice 1, then post:

```json
{"reference":"purchase-payment-1","date":"2026-08-01","description":"Settle supplier bill","transaction_id":2,"invoice_ids":[1],"lines":[{"account":"2000","debit_cents":11000},{"account":"1000","credit_cents":11000}],"gst":{"label":"excluded","gross_cents":0,"gst_cents":0,"status":"reviewed","attribution_date":"2026-08-01","evidence":"Settlement of already recognised purchase; confirmed match"}}
```

A partial payment uses its actual amount in both settlement lines; GST is not claimed again. A grouped settlement lists all relevant invoice_ids and exactly reconciles confirmed matches. No amount may be both recognised and expensed again at payment.

## Sale/RCTI AUD110 including GST10

Import role=sale with customer contact. Recognition: debit 1100 receivables 11000, credit 4000 sales 10000 and 2100 GST payable 1000. Label sale, gross 11000, GST1000, invoice_ids and verified attribution evidence. On matched receipt: debit bank1000 and credit receivables1100; label excluded, zero gross/GST. Do not credit sales again.

## Exceptions and limits

- Unknown entitlement remains pending; business allocations are reviewed separately.
- A deferred/excluded document needs a period-specific documented reason via review-document; no arbitrary silent omission.
- Prior-period invoices require evidence of prior recognition/claim or justified later attribution, not automatic re-claiming.
- Credit notes use sale_refund/purchase_refund and positive metadata, reverse ledger direction and retain original evidence links. Automatic refund payment matching is not supported.
- Opening receivables/payables and payments before invoices need explicit accounting review; do not fabricate prior-period revenue or duplicate GST.
- Split recognition of a single accrual document and zero-activity account evidence are not automated in this version.

Sources: [ATO non-cash attribution](https://www.ato.gov.au/law/view/document?LocID=%22GST%2FGSTR200013%2FNAT%2FATO%2Ffp24%22&PiT=20241204000001), [Simpler BAS](https://softwaredevelopers.ato.gov.au/SimplerBAS). Recheck current guidance and applicability before tax treatment.
