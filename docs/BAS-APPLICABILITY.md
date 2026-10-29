# BAS applicability assessment

Implemented first stage of the BAS checklist gap review: sixteen period-specific scope questions, confirmed answer/evidence/provenance records, append-only history, stale-answer detection, actionable review CSVs and readiness blockers. Existing databases gain an additive bas_applicability_events table on normal helper connection. Original statements and invoices are preserved.

Commands:

```sh
python3 accounting_core/accounting_store.py --db /path/accounting/db/accounting.db bas-applicability --start 2026-07-01 --end 2026-09-30
python3 accounting_core/accounting_store.py --db /path/accounting/db/accounting.db save-bas-applicability --request answers.json
```

Each answer names a catalog topic, yes/no/unknown, a specific evidence note and user_confirmed/source_verified/unknown provenance. Supply business_id and exact period. Unanswered questions never default to no. Replies do not carry automatically between businesses or periods. Newly imported period transactions, any workspace invoices (including earlier/later dates relevant to attribution), profile or reporting-scope changes require rechecking saved answers.

The UI shows the unanswered question or an actual follow-up. Unsupported additional BAS calculations keep readiness blocked. There is deliberately no checkbox that declares calculation complete. Complete assessment and completed BAS are different statuses. Future work must implement control reconciliations, additional BAS labels and formal finalisation. Annual tax-return preparation remains separate.

## Supported event review completion

`complete-bas-task --request review.json` records an explicitly confirmed review for a current yes transaction-event answer. Required: business_id, start, end, topic, actual reviewer, specific conclusion, confirmed=true and nonempty workspace evidence_files. Saves append-only bas_task_reviews plus audit events; hashes supporting files and the accounting state. Current completions clear their scope blocker only. Changed/missing files, changed accounting entries or a replacement answer require re-review. CSV includes reviewer, conclusion and supporting evidence. No additional tax-label calculations, lodgement approval or legal validation is implied. The seven obligation topics remain unsupported and blocked. File existence alone does not validate treatment; the owning skill must review and post necessary accounting changes before requesting confirmation.
