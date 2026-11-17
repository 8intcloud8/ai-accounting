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
## Accounting: always end with a question for the next step

Work like Claude Code: do the work, say briefly what you did, then end with one question that starts the next piece of work, for example: "Shall I classify the 275 uncategorised transactions now?"

- Commands that change the books return `next_step.end_your_reply_with`: make it, word for word, the last line of your reply. Never swap in your own question.
- Do not list the steps or everything still open. One specific question only.
- Never end with only a summary, or with a promise such as "I'll continue with…": do the work or ask.
- If the user has said to keep going, do that work instead of asking.
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
