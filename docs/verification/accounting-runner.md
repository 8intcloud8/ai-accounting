# Supervised accounting runner — 11 November 2026

Acceptance: after a Codex turn ends, inspect persisted Case Tracker/ledger state and launch another turn if supported work remains. Preserve approvals. Continue independent work around user questions. Stop on explicit approval needs, errors, repeated unchanged state, or configured limits. Save local progress and diagnostic logs; prevent overlapping runners.

Implemented accounting_core/accounting_runner.py and installed manage-accounting 0.1.6. The skill launches this runner for authorized whole-period execution; worker turns do not launch nested runners. Uses sandboxed ephemeral Codex CLI with structured outputs, no approval bypass. Default 40 turns, 900 seconds per turn, two consecutive unchanged turns before no_progress. A per-workspace lock prevents concurrent supervisors. Process groups are terminated on timeout/interruption and unsuccessful exit before releasing the lock. Successful turns may preserve read-only browser report servers; workers must not start background accounting writes. SIGTERM raises interruption for active-worker cleanup.

Five tests passed: repeated continuation, unchanged promise-only response retried then stopped, approval halts without retry, needs_user does not stop independent work, timeout kills the worker. Lint passes. First live installed run in /private/tmp/accounting-runner-live-demo stopped for actual missing sources, preserving document and statement blockers. A second live run in /private/tmp/accounting-runner-live-multiturn automatically launched turn 2 (statements) after turn 1 (documents) ended. No production data is used.

Uses Codex's documented non-interactive structured output and sandbox options: https://learn.chatgpt.com/docs/non-interactive-mode

Limitations: this supervises the CLI turns it launches; it is not a desktop stop hook. Tool connections and approval capabilities must exist in that CLI environment. Checkpoint/evidence validation is not a tax accuracy guarantee. Logs can contain private case metadata and remain in selected workspace/output/runner. Completed step claims still require the producing skill's evidence checks. Production end-to-end BAS not yet validated by this change.

Regression: ten Case Tracker tests and four release tests also passed. Installed manage-accounting 0.1.6 ships the supervisor and matches canonical source. Live test is labelled isolated demo, not a full BAS or tax accuracy evaluation. macOS/Unix locking/process groups are used; Windows runner support is not implemented.

Final live result: two real Codex turns, both persisted changes; runner stopped needs_user only after no independent action remained. Documents and statements blockers retained. Result: /private/tmp/accounting-runner-live-multiturn/output/runner/20261111-180009-9105/result.json

## Step order, partial steps and stop summary — 11 November 2026

Ticket: runner stalled after 2 turns (blocked document review gated invoices → classification; empty stop message; sandbox failure asked as user question). Expected: classification starts once statements done; drafted steps save `partial`; environment/approval outcomes park; stop message groups answers/approvals/environment; intake questions emitted at start.

Run 1 (manage-accounting 0.1.6 installed, CBA Q3 workspace): first action invoices (not stop); `questions_now` emitted; but invoices `partial` rerun 4× — fixed: partial with no inputs waits for user; revision counters excluded from progress fingerprint. Run 2: classification ran, saved `partial` with 58 proposals + Excel review; runner stopped needs_user after 1 turn with summary (done / drafted-waiting / answer list). Pass. Unverified: environment and approval branches live (unit-tested only); old documents blocker predates `Environment:` prefix so still listed as a question. 111 tests pass; installed files match source.
