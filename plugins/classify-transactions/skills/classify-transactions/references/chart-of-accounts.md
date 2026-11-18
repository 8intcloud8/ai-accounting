# Chart of accounts (Xero-style, Australia)

The workspace uses the codes and names of Xero's Australian default chart, so a file moves
to Xero without recoding. Pick the most specific account that fits the evidence; use 429
General Expenses only when nothing below fits, and say why. The account is the category
only: GST treatment is decided separately from the evidence and ATO guidance on every
journal (`gst.label`, `gst_cents`), never from the account.

## Special accounts (the engine relies on these)

| Code | Name | Use |
|---|---|---|
| 090 | Business Bank Account | The bank side of every bank-linked journal (all imported accounts). |
| 820 | GST | The single GST account: credit GST on sales, debit GST on purchases. |
| 610 | Accounts Receivable | Accrual sales recognised before payment. |
| 800 | Accounts Payable | Accrual purchases recognised before payment. |
| 880 | Owner A Drawings | Owner/private money taken out; the transaction shows as Personal. |
| 881 | Owner A Funds Introduced | Owner money put in; shows as Personal. |
| 900 | Loan | Loans, including director loans (company money spent privately, or owner lending). |

## Income

| Code | Name | Typical use |
|---|---|---|
| 200 | Sales | Sales of goods/services, RCTIs from clients. |
| 260 | Other Revenue | Other business income (e.g. grants, recoveries). |
| 270 | Interest Income | Bank interest (input taxed: no GST). |

## Expenses

| Code | Name | Typical use |
|---|---|---|
| 310 | Cost of Goods Sold | Stock or materials resold or used in sales. |
| 400 | Advertising | Ads, marketing, promotion. |
| 404 | Bank Fees | Account, card, merchant and international transaction fees. |
| 408 | Cleaning | Cleaning services and supplies. |
| 412 | Consulting & Accounting | Accountant, bookkeeper, tax agent, business consultants. |
| 416 | Depreciation | Depreciation journals only. |
| 420 | Entertainment | Meals and entertainment (check FBT/income tax and GST credit limits). |
| 425 | Freight & Courier | Postage, couriers, freight. |
| 429 | General Expenses | Business costs that fit no specific account. |
| 433 | Insurance | Business insurance premiums. |
| 437 | Interest Expense | Interest on business loans and cards. |
| 441 | Legal expenses | Lawyers, ASIC/company fees when legal in nature. |
| 445 | Light, Power, Heating | Electricity, gas. |
| 449 | Motor Vehicle Expenses | Fuel, rego, servicing, tolls, parking for business vehicles. |
| 453 | Office Expenses | Small office items and consumables. |
| 461 | Printing & Stationery | Printing, stationery. |
| 469 | Rent | Office or premises rent. |
| 473 | Repairs and Maintenance | Repairs to business property and equipment. |
| 477 | Wages and Salaries | Employee and director wages (gross). |
| 478 | Superannuation | Super guarantee and other employer super. |
| 485 | Subscriptions | Software/SaaS, cloud services, memberships, publications. |
| 489 | Telephone & Internet | Mobile, landline, internet services. |
| 493 | Travel - National | Domestic flights, accommodation, taxis/rideshare for business travel. |
| 494 | Travel - International | Overseas travel (usually no GST). |

## Assets and liabilities

| Code | Name | Typical use |
|---|---|---|
| 620 | Prepayments | Amounts paid in advance for later periods. |
| 710 | Office Equipment | Furniture and office equipment held as assets. |
| 720 | Computer Equipment | Computers and devices held as assets. |
| 801 | Unpaid Expense Claims | Expenses paid personally, owed back by the business. |
| 825 | PAYG Withholdings Payable | Tax withheld from wages, until paid to the ATO. |
| 826 | Superannuation Payable | Super owed, until paid to the fund. |
| 830 | Income Tax Payable | Company income tax owed. |
| 850 | Suspense | Temporary holding only, never a final category. |
| 960 | Retained Earnings | Year-end only. |
| 970 | Owner A Share Capital | Share capital paid in. |

Workspaces made before this chart were renumbered automatically (backup kept in
`backups/before-xero-chart-*.zip`): 1000→090, 1100→610, 1200 and 2100→820, 1500→710,
2000→800, 2200→900, 3000→880, 4000→200, 4900→260, 5000→429, 5100→445, 5200→493, 5300→433.
Accounts that were filed under 429 General Expenses during that move may deserve a more
specific account; reclassify only with a reversal and replacement journal.
