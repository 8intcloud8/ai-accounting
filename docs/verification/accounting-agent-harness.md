# Accounting agent harness verification — 9 November 2026

Acceptance recorded for this change: persist facts with entity/date/source and corrections; persist separate BAS/tax cases; resume without repeated facts; route ready skills while blocked items remain; invalidate stale evidence and memory; preserve ledger boundaries; install and exercise manage-accounting normally; provide a visible isolated demonstration.

Implementation: memory_store.py and agent_harness.py, orchestrated by installed manage-accounting; all other skills consult shared case memory. Memory and workflow state live in selected workspace db/memory.db. Operational ledger remains separate. No autonomous background worker or lodgment engine is claimed.

Eight isolated tests passed: persistence/idempotent case creation, entity isolation, date-effective corrections, stale revision rejection, memory invalidation, source/dependency invalidation, independent ready work during a blocker, malformed input and static symlink rejection, expiry/withdrawal and a concurrent memory change before completion. Build passed; all 17 plugin installs and shipped Python/Markdown files verified against source.

Source review identified missing memory invalidation and result-completion concurrency protection; both addressed with recorded memory revisions and required expected_revision tokens for done events. File hashes establish artifact identity, not substantive tax correctness. Full production BAS processing remains a separate end-to-end acceptance task.
