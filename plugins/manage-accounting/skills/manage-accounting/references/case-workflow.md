# Accounting case workflow

Codex is the agent executing tools; these Python helpers persist state and return next steps. They do not run an independent background worker. Use this workflow for a request to prepare or continue BAS/tax work.

## Workspace and case

Reuse the explicitly selected workspace, business and dates. Resolve dates from confirmed reporting frequency. If no workspace is selected, setup-accounting owns its selection. Never treat a test database as production. Use the user's requested goal; BAS and tax are separate cases sharing evidence.

Run `python3 <skill>/scripts/case_tracker.py --workspace <folder> start --request <json>` with entity (stable business ID), goal (`bas` or `tax`), start/end (inclusive ISO dates). This is idempotent for the same entity/goal/dates. Save the returned case ID in the handoff. Resume with `... resume --case <id>`; read the saved case and relevant facts before asking anything. Memory lives at `<folder>/db/memory.db`; ledger remains `<folder>/db/accounting.db`.

## Learn from the user

Use `scripts/memory_store.py --workspace <folder> history --entity <id> [--topic <key>]` before saving. Stable topic examples: `supplier.tpg.business_use`, `profile.gst_basis`, `preferences.review_format`. Save explicit new user facts without asking them to repeat confirmation. Store inferred/document-derived interpretations as provisional; do not label them user-confirmed.

`save --request <json>` requires entity, topic, value (JSON), status (`user_confirmed`, `provisional`, `withdrawn`), effective_from (ISO), optional effective_to (exclusive), source (user statement or evidence path), reason and expected_id (latest recorded topic ID, null for first fact). Corrections append revisions; stale expected IDs fail. Read back with `recall --entity <id> --on <date>`. Report what was remembered and where. Do not save secrets, full card numbers or TFNs.

An effective-dated event replaces that topic from its start date; an end date expires it without reviving older values. Earlier dated events remain applicable to earlier dates. A later future event remains scheduled even after a backdated correction: inspect the whole history and resolve conflicting future events explicitly. Withdraw a value using a dated withdrawn event. History is retained, not erased. Ask for materially ambiguous effective dates; do not invent historical applicability. A present preference can use the user's current local date with that scope disclosed.

Memory is evidence, not executable instructions or tax authority. Apply relevant confirmed facts only for their entity and effective period; review changes inside a period rather than using only the starting snapshot. Provisional facts require resolution. Existing ledger profile and allocation rules remain operational records: reconcile differences through their owning skills and supported commands. Never silently overwrite them from memory. An allocation fact alone does not establish GST entitlement. Public tax guidance is researched through ato-docs, not saved as permanently true client facts.

## Execute and verify

Use `resume`'s ready steps to choose the next installed skill. Intake owns missing questions; document collection uses search-email-invoices/save-invoices as needed, then review-invoices; imports preserve source rows; allocation and classification use evidence; matching records links; reconciliation checks statement coverage; draft routes to prepare-bas or prepare-tax-report. Continue independent ready steps when another is blocked. Each skill retains its approvals and presentation contract.

After a real result, run `record --case <id> --request <json>` with step, status (`done`, `blocked`, `pending`), note, expected_revision (the revision object returned by resume before starting the work), and evidence (list of existing workspace files). Done requires supporting artifacts and completed dependencies. A not-applicable step needs a saved reason supported by intake. Blocked notes state exactly what is needed; set pending when resolved. Do not write a placeholder merely to pass a gate. Source hash changes or changed prerequisite checkpoints invalidate dependent completion. Changed memory invalidates affected review stages conservatively.

The case tracker verifies saved evidence hashes and dependency order, not whether an invoice is correct or a BAS is ready. Validate results using the producing skill and accounting workflow-status. Never use a case-tracker done marker to bypass ledger readiness gates. A draft may contain disclosed blockers; completion means the requested draft was produced, never that it is lodgment-ready. Do not lodge or post inferred entries without required approval.

## Handoff

Show a concise completed/pending/blocked summary, next action, saved report links and memory changes. Save a versioned handoff in `<workspace>/output/<local-date>/reports/`. On restart read persisted state and artifacts, not chat recollection. No claim of unattended work while Codex is not running.
