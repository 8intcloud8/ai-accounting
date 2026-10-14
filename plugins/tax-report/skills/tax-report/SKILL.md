---
name: tax-report
description: Produce a local bookkeeping trial balance and income/expense workpaper for annual tax review.
---

# Tax Report

Resolve entity and financial-year dates. Run `scripts/accounting_store.py tax-report --start YYYY-MM-DD --end YYYY-MM-DD` against the selected workspace. Show account balances, unresolved classifications and saved CSV/JSON.

This is an accounting workpaper, not a tax payable calculation or lodged return. Separately review capital assets/depreciation, non-deductible items, private use, reimbursements, losses and entity-specific tax adjustments using current ATO guidance. Keep company and individual returns distinct. Income-tax and GST timing can differ; do not relabel cash movements as accrual profit.

Do not claim a complete income statement or balance sheet without opening balances and all accrual/adjustment entries. Record tax_adjustments completion only after an actual documented review, and retain outstanding unsupported calculations explicitly.
