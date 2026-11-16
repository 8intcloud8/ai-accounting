"""The accounting rules Codex reads on every turn, kept in the workspace AGENTS.md.

Skills are read only when started, so a quick follow-up ("drop that bill") runs
without them. AGENTS.md is loaded for every turn in the workspace, so the rule that
every reply ends with the open steps and one next question lives here too. Only the
block between the markers is ours; anything else in the file is the user's.
"""

from pathlib import Path

START = "<!-- ai-accounting:start -->"
END = "<!-- ai-accounting:end -->"
BLOCK = f"""{START}
## Accounting: always end with the next step

After every reply that changes, corrects or answers anything about the books, even a short correction:

1. Run `workflow-status --start --end` for the period (the manage-accounting skill shows how).
2. In the reply itself, list each open step on its own line, lowest first, saying what is open and where it gets fixed, for example: "Step 4 Transactions: 12 payments still need a category."
3. End with one question that starts the first open step: "Shall I start Step 4: Transactions now?" If the user has said to keep going, start it instead of asking.

Never end a reply with only a summary of what changed, and never end with a promise such as "I'll continue with…": do that work now or ask the question. If nothing is open, say so and offer the BAS draft.

Steps: 1 Setup, 2 Bank statements, 3 Invoices, 4 Transactions, 5 Payroll and BAS items, 6 Reconciliation, 7 BAS draft.
{END}
"""


def merged(existing: str) -> str:
    """`existing` with our block added or replaced; the user's text is untouched."""
    if START in existing and END in existing:
        before, _, rest = existing.partition(START)
        _, _, after = rest.partition(END)
        return before + BLOCK.rstrip("\n") + after
    if not existing.strip():
        return BLOCK
    return existing.rstrip("\n") + "\n\n" + BLOCK


def ensure(root: Path) -> Path:
    """Write or refresh the block in `<root>/AGENTS.md`. Returns the file path."""
    target = Path(root) / "AGENTS.md"
    existing = target.read_text() if target.exists() else ""
    updated = merged(existing)
    if updated != existing:
        temp = target.with_name(".AGENTS.md.tmp")
        temp.write_text(updated)
        temp.replace(target)
    return target
