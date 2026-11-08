# Overlap fixes — 8 November 2026

Acceptance: single owners for period intake, transaction review workbook, invoice import and reimbursement state; coordinator includes intake and document review; tax research uses shared skill; detail follows report contracts.

Updated and natively reinstalled 16 consumers; schemas validated and installed SKILL.md files byte-matched source. Package build passed. Alternate direct search skill synchronized.

A fresh read-only invocation read six installed skills and correctly routed period questions, existing-workbook continuation, extraction and reimbursements. This verifies routing only, not live imports or ledger posting. No client accounting records changed.

Bundled shared references and runtime copies remain for standalone installs. Older external Xero cache was not removed; its enabled registration and dependencies still require review before cleanup. No claim of eliminating every duplicate installation.

## Observed routing result

Read all six installed skills. Routing:

| Skill | Responsibility |
|---|---|
| **manage-accounting** | Resume existing workspace and period; inspect saved status/blockers, reuse confirmed quarterly profile, coordinate next steps. |
| **grill-me-tax** | Collect **missing/stale period obligations**; reuse supported answers. Read `bas-applicability`, persist confirmations through `save-bas-applicability`. Profile changes route to setup-accounting. |
| **extract-bankstatements** | Import/validate missing statements; preserve every source transaction. Hand classification/workbook work onward. |
| **classify-transactions** | **Continue existing Excel workbook**; preserve edits, IDs, confirmations and exclusions. Own purpose/category/GST proposals, requested workbook-edit application and confirmed journal posting. Save a versioned workbook; no replacement HTML. |
| **extract-invoices** | Read/import invoice facts and evidence. Does not approve claims or record reimbursements. |
| **match-payments** | Propose matches; save allocations after explicit confirmation. **Own payment source, claim approval, unreimbursed status and reimbursements** through `record-purchase`. |

Continuation: inspect saved progress → fill intake gaps while continuing supported transaction review → import missing evidence → update existing workbook → confirm matches/classifications → reconcile → prepare draft BAS after completeness/PAYG/adjustment checks.

Personal-card purchase and company reimbursement stay separate. Match reimbursement to its **claim**, reuse its payment reference; **classify-transactions posts associated journals**. Recording reimbursement neither pays money nor posts journals.

No accounting operations or browsing performed. Routing verified against installed skills.
