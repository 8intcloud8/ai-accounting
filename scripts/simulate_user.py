#!/usr/bin/env python3
"""Test harness: play the user against accounting_runner until the period finishes.

Each time the runner stops for answers or approvals, one Codex turn answers from a
fixed answers file through the owning skills, then the runner resumes. Refuses any
workspace without a .simulated-user-ok marker so real books are never auto-approved.
Not shipped in plugins.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))
import accounting_runner as runner  # noqa: E402

MARKER = ".simulated-user-ok"
DEFAULT_ANSWERS = Path(__file__).resolve().parents[1] / "tests/fixtures/simulated_answers.json"
DONE = ("finished",)
FATAL = ("error", "no_progress", "turn_limit")
STOP_SCHEMA = {
    "type": "object",
    "properties": {
        "answered": {"type": "array", "items": {"type": "string"}},
        "unanswerable": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answered", "unanswerable"],
    "additionalProperties": False,
}


def user_prompt(root, result, answers):
    return (
        f"You are the SIMULATED USER for the test accounting workspace {root}. "
        "This workspace is test data; the real user has authorised you to answer and approve on their behalf here only. "
        "Use installed manage-accounting and the owning skills (grill-me-tax for intake, the stage skill for approvals) to save each answer, "
        "exactly as a user reply would be saved. Answer from this answers file; where it gives a default, use it for unlisted questions:\n"
        + json.dumps(answers)
        + "\nApprove proposals only as the answers file allows. Never edit source documents or databases directly, never lodge. "
        "Do not run accounting_runner.py. List each question you answered and any you could not.\n"
        "Runner stop to answer:\n"
        + json.dumps({k: result.get(k) for k in ("stop", "message", "questions")})
    )


def answer(root, result, answers, codex, folder, round_no, timeout):
    schema = folder / "user-schema.json"
    schema.write_text(json.dumps(STOP_SCHEMA))
    response, log = folder / f"user-{round_no}.json", folder / f"user-{round_no}.log"
    with log.open("w") as stream:
        code = runner.execute(
            [codex, "exec", "--ephemeral", *runner.SANDBOX, "-C", str(root), "--skip-git-repo-check",
             "--output-schema", str(schema), "-o", str(response), user_prompt(root, result, answers)],
            stream, timeout,
        )
    if code:
        raise RuntimeError(f"Simulated user turn exited {code}; inspect {log}")
    return json.loads(response.read_text())


def simulate(workspace, request, answers, codex, rounds=8, turns=20, timeout=900):
    root = Path(workspace).expanduser().resolve()
    if not (root / MARKER).is_file():
        raise ValueError(f"Refusing: {root} lacks {MARKER}; only marked test workspaces may be auto-answered")
    folder = root / "output" / "simulation"
    folder.mkdir(parents=True, exist_ok=True)
    report = []
    last = None
    for round_no in range(1, rounds + 1):
        result = runner.run(root, request, codex, max_turns=turns, timeout=timeout)
        entry = {"round": round_no, "stop": result["stop"], "message": result["message"],
                 "run_folder": result["run_folder"],
                 "progress": {p["code"]: p["count"] for p in result["state"].get("problems", [])}}
        report.append(entry)
        if result["stop"] in DONE or result["stop"] in FATAL:
            break
        if entry["progress"] == last:
            entry["stop"] = "answers_changed_nothing"
            break
        last = entry["progress"]
        entry["user"] = answer(root, result, answers, codex, folder, round_no, timeout)
    (folder / "report.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--goal", choices=("bas", "tax"), default="bas")
    parser.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--turns", type=int, default=20, help="runner turns per round")
    args = parser.parse_args()
    codex = shutil.which("codex")
    if not codex:
        parser.error("Codex CLI is required")
    request = {"start": args.start, "end": args.end, "goal": args.goal, "entity": None}
    try:
        report = simulate(args.workspace, request, json.loads(args.answers.read_text()), codex,
                          args.rounds, args.turns)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Simulation failed: {exc}\n")
    for entry in report:
        print(f"round {entry['round']}: {entry['stop']}  {entry['progress']}")


if __name__ == "__main__":
    main()
