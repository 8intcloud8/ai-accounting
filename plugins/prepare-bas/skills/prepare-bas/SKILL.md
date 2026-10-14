---
name: prepare-bas
description: Produce an Australian Simpler BAS GST review workpaper from reviewed local ledger entries and list missing evidence.
---

# Prepare BAS

Resolve workspace, entity and reporting period. Read references/ato-guidance.md and refresh official guidance before tax treatment. Confirm registration and cash/accrual basis from the stored profile. The initial implementation covers Simpler BAS GST subtotals G1, 1A and 1B; PAYG and other labels need separate review.

Run `scripts/accounting_store.py prepare-bas --start YYYY-MM-DD --end YYYY-MM-DD`. The engine selects reviewed GST items by explicit attribution date, excludes reversed journals, subtracts refund adjustments, and saves immutable report snapshots plus dated JSON/CSV exports. Unknown/unreviewed items are blockers, not zero GST.

Present reviewed subtotals in dollars, pending items, reconciliation status and source references. Always identify output as a draft workpaper. `ready_for_review` means internal checks passed, not that a return has been lodged or professionally certified. Full BAS completion, special GST schemes and electronic lodgement are outside this version. Never turn partial subtotals into a final amount payable.
