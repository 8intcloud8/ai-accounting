import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))
import accounting_runner as runner

REQUEST = {"start": "2026-07-01", "end": "2026-09-30", "goal": "bas"}


def problem(code, who, count=1, text=None):
    skill = {"transactions_unclassified": "classify-transactions",
             "reconciliation_required": "reconcile-accounts",
             "intake_question": "grill-me-tax"}.get(code, "x")
    return {"code": code, "skill": skill, "who": who, "count": count, "text": text or f"{code} {count}"}


def state(*problems, drafted=False):
    return {"setup_missing": False, "problems": list(problems), "drafted": drafted}


def reply(outcome="continue", questions=()):
    def worker(command, *args):
        Path(command[command.index("-o") + 1]).write_text(
            json.dumps(dict(outcome=outcome, message=outcome, questions=list(questions))))
        return 0
    return worker


class RunnerTests(unittest.TestCase):
    def run_with(self, states, worker, **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            states = iter(states)
            with (patch.object(runner, "read_state", side_effect=lambda *a: next(states)),
                  patch.object(runner, "execute", side_effect=worker) as calls):
                return runner.run(folder, REQUEST, "codex", **kwargs), calls

    def test_fixes_worker_problems_in_order_then_stops_for_user(self):
        result, calls = self.run_with(
            [state(problem("intake_question", "user"), problem("transactions_unclassified", "worker", 58)),
             state(problem("intake_question", "user"), problem("transactions_unclassified", "worker", 10)),
             state(problem("intake_question", "user"))],
            reply())
        self.assertEqual("needs_user", result["stop"])
        self.assertEqual(2, calls.call_count)
        self.assertIn("intake_question 1", result["message"])

    def test_stuck_worker_problem_is_set_aside_not_retried(self):
        stuck = problem("transactions_unclassified", "worker", 58)
        recon = problem("reconciliation_required", "worker")
        result, calls = self.run_with(
            [state(stuck, recon), state(stuck, recon), state(stuck)], reply())
        self.assertEqual(2, calls.call_count)  # classification once, then reconciliation
        self.assertEqual("needs_user", result["stop"])
        self.assertIn("Workers could not clear these", result["message"])

    def test_approval_and_environment_are_grouped(self):
        a = problem("transactions_unclassified", "worker")
        b = problem("reconciliation_required", "worker")
        replies = iter([reply("needs_approval", ["Approve 58 proposals?"]),
                        reply("environment", ["Loopback blocked"])])
        result, calls = self.run_with([state(a, b), state(a, b), state(a, b)],
                                      lambda *args: next(replies)(*args))
        self.assertEqual(["Approve 58 proposals?"], result["questions"]["needs_approval"])
        self.assertEqual(["Loopback blocked"], result["questions"]["environment"])
        self.assertIn("Environment problems", result["message"])
        command = calls.call_args_list[0].args[0]
        self.assertIn("sandbox_workspace_write.network_access=true", command)

    def test_runs_draft_when_clear_then_finishes(self):
        result, calls = self.run_with([state(), state(drafted=True)], reply())
        self.assertEqual("finished", result["stop"])
        self.assertEqual("prepare-bas", result["turns"][0]["action"]["skill"])

    def test_setup_missing_stops_without_worker(self):
        result, calls = self.run_with([{"setup_missing": True, "problems": []}], reply())
        self.assertEqual("needs_user", result["stop"])
        self.assertEqual(0, calls.call_count)

    def test_timeout_terminates_worker(self):
        import subprocess

        with tempfile.TemporaryFile(mode="w+") as stream:
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.execute([sys.executable, "-c", "import time; time.sleep(20)"], stream, 0.1)


class MemoryTests(unittest.TestCase):
    def test_memory_rejects_progress_notes(self):
        import memory_store

        with tempfile.TemporaryDirectory() as folder:
            fact = dict(entity="demo", topic="worker.classification", value={"done": 3},
                        status="provisional", effective_from="2026-07-01", source="x", reason="x")
            with self.assertRaises(ValueError):
                memory_store.save(folder, fact)
            memory_store.save(folder, dict(fact, topic="supplier.acme.gst"))


class LedgerStateTests(unittest.TestCase):
    def test_reads_problems_and_proposals_from_ledger(self):
        import accounting_store as store

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertTrue(runner.read_state(root, REQUEST)["setup_missing"])
            (root / "db").mkdir()
            db = root / "db" / "accounting.db"
            profile = root / "profile.json"
            profile.write_text(json.dumps({"business_id": "demo", "legal_name": "Demo Pty Ltd",
                                           "entity_type": "company", "gst_registered": True, "gst_basis": "cash"}))
            store.dispatch(type("A", (), dict(command="setup-accounting", db=db, request=profile))(), store.connect)
            codes = {p["code"]: p for p in runner.read_state(root, REQUEST)["problems"]}
            self.assertEqual("user", codes["intake_question"]["who"])
            self.assertEqual("worker", codes["bank_missing"]["who"])


if __name__ == "__main__":
    unittest.main()
