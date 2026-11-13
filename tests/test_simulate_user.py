import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import simulate_user as sim


def stop(kind, steps):
    return {"stop": kind, "message": kind, "run_folder": "x", "questions": {},
            "state": {"problems": [{"code": s, "count": v} for s, v in steps.items()]}}


class SimulateUserTests(unittest.TestCase):
    def test_refuses_unmarked_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                sim.simulate(folder, {}, {}, "codex")

    def test_answers_until_finished(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, sim.MARKER).touch()
            runs = iter([stop("needs_user", {"intake": 3}),
                         stop("needs_approval", {"proposals": 5}),
                         stop("finished", {})])
            with (patch.object(sim.runner, "run", side_effect=lambda *a, **k: next(runs)),
                  patch.object(sim, "answer", return_value={"answered": ["q"], "unanswerable": []}) as user):
                report = sim.simulate(folder, {}, {}, "codex")
            self.assertEqual(["needs_user", "needs_approval", "finished"], [r["stop"] for r in report])
            self.assertEqual(2, user.call_count)
            self.assertTrue(Path(folder, "output/simulation/report.json").is_file())

    def test_stops_when_answers_change_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, sim.MARKER).touch()
            same = {"intake": 3}
            with (patch.object(sim.runner, "run", side_effect=lambda *a, **k: stop("needs_user", same)),
                  patch.object(sim, "answer", return_value={"answered": [], "unanswerable": ["q"]}) as user):
                report = sim.simulate(folder, {}, {}, "codex")
            self.assertEqual("answers_changed_nothing", report[-1]["stop"])
            self.assertEqual(1, user.call_count)


if __name__ == "__main__":
    unittest.main()
