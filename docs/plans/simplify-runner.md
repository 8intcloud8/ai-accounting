# Plan: one source of truth for the BAS runner

## Goal

One command takes a period from bank statement to BAS draft. It does all the work it can, stops once with every question and approval, and resumes on its own after you answer.

## The problem

"What's done" lives in two places that disagree:

| Accounting database (`status_report`) | Case tracker checklist |
|---|---|
| Counts real work left: unclassified transactions, unreviewed invoices, unreconciled accounts, missing intake answers | Stores a status per step: done, partial, blocked, pending, stale |
| Changes when data changes | Changes only when a worker remembers to update it |

Every bug in the last runs came from keeping these in sync: steps "done" with open work, `partial` steps waiting forever, answers saved that the checklist never noticed, and problems matched to steps by searching their wording.

## The design

**The database is the only source of truth.** The runner asks one question each turn: "what is the first open problem, and can a skill fix it without the user?"

Each problem in `status_report` gets a **code**, an **owning skill** and a **who** (worker or user), set where the problem is created, so nothing searches message wording:

| Problem (code) | Skill | Who |
|---|---|---|
| `setup_missing` | setup-accounting | user |
| `intake_question` (BAS scope, method, GST profile) | grill-me-tax | user |
| `invoices_unread` (files in documents/invoices not yet extracted) | extract-invoices | worker |
| `invoice_review` (extracted, needs a decision) | extract-invoices | user |
| `bank_missing` | extract-bankstatements | worker |
| `transactions_unclassified` | classify-transactions | worker |
| `proposals_awaiting_approval` | classify-transactions / match-payments | user |
| `gst_pending` | classify-transactions | worker |
| `reconciliation_required` | reconcile-accounts | worker |
| `review_required` (completeness, PAYG, adjustments) | manage-accounting | user |
| everything clear | prepare-bas | worker, then stop with the draft |

**Runner loop:**
1. Read the problems.
2. If any **worker** problem exists, run its skill, then go to 1.
3. If only **user** problems remain, stop and show them all at once.
4. If the same worker problem survives two turns unchanged, stop: the skill is stuck.

**Answering:** you answer through the owning skill, which writes to the database. That removes the problem, so the next run moves on. No checklist to update and no "resume" step.

**Drafting before answers:** a worker that can't finish (say, classification needs a business-use answer) saves its proposals in the database and adds `proposals_awaiting_approval`. That problem belongs to the user, so the runner moves on to other worker problems. Nothing is called `partial`.

**Environment failures** (sandbox, missing connector): the worker reports them; the runner lists them separately and never treats them as questions.

## What changes

- **Remove:** case tracker step statuses (`done`, `partial`, `blocked`, `stale`), the step-order rules, the `LEDGER_STEPS` wording matcher and `record` calls in skills.
- **Keep:** memory facts (saved answers), the runner's turn limit, timeouts, workspace lock and grouped stop message, and the fake user for testing.
- **Add:** a code, skill and who on each problem in `status_report`. Classification and matching proposals are stored in the database, not only in Excel.
- **Skills:** stop calling case tracker `record`. Each skill only writes accounting data, which it already does.

## How we'll know it works

1. **Unit tests:** each problem maps to one skill; answering a question removes its problem; a stuck worker stops after two turns.
2. **Fake user live run** on the CBA test workspace reaches a BAS draft, or stops on a named, real gap (e.g. NAB statements missing).
3. The answers file gives a business purpose per supplier, so the draft isn't empty.

## Decisions for you

1. **Remove case tracker checkpoints entirely?** Recommended: yes. Keep memory facts.
2. **Store classification proposals in the database?** Recommended: yes. They're needed for "awaiting approval" to be a real problem.
3. **Document review (review-invoices):** recommended to make it optional housekeeping that never blocks the BAS.
