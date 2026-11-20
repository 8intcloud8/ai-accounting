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
## Accounting: keep working; stop only when you need the user

Work like Claude Code: do all the work the records support without asking permission, and stop only for a fact only the user knows, a missing document, or their OK to post.

- Commands that change the books return `next_step`: when `keep_going` is true, do `do_next` now; when false, ask everything you need in one message and end with `end_your_reply_with`.
- Never show step numbers, step lists or progress summaries. Results and decisions go in the chat.
- Never ask "shall I…" for work you can do, and never end with a promise such as "I'll continue with…".
- On Windows, run `python3` commands as `py -3` (or `python` if `py` is missing).
- When the user states a lasting fact ("Aldi is always personal"), save it in case memory with manage-accounting's `references/case-workflow.md` (a supplier's purpose is topic `supplier.<name>.purpose`), never as a loose note file.
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
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    updated = merged(existing)
    if updated != existing:
        temp = target.with_name(".AGENTS.md.tmp")
        temp.write_text(updated, encoding="utf-8")
        temp.replace(target)
    return target
