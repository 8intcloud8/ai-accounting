"""The setup check reports what a fresh computer is missing, in plain words."""

import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "accounting_core"))
import check_environment as check  # noqa: E402

SOURCE = ROOT / "accounting_core/check_environment.py"


class CheckEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        patcher = mock.patch.dict(os.environ, {"CODEX_HOME": self.home.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_script_parses_on_old_python_so_it_can_report_instead_of_crash(self):
        ast.parse(SOURCE.read_text(), feature_version=(3, 8))

    @unittest.skipUnless(os.access("/usr/bin/python3", os.X_OK), "no system Python")
    def test_system_python_gets_a_plain_answer(self):
        result = subprocess.run(["/usr/bin/python3", str(SOURCE), "status"], capture_output=True, text=True,
                                env=dict(os.environ, CODEX_HOME=self.home.name))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"python_ok"', result.stdout)

    def test_old_python_is_told_where_to_download(self):
        with mock.patch.object(check.sys, "version_info", (3, 9, 6)):
            result = check.status()
        self.assertFalse(result["ready"] or result["can_install_packages"])
        self.assertIn("python.org/downloads", result["messages"][0])
        self.assertIn("3.9", result["messages"][0])

    def test_missing_packages_and_node_are_reported_separately(self):
        with mock.patch.object(check, "has_package", side_effect=lambda name: name != "pdfplumber"), \
                mock.patch.object(check, "find_node", return_value=None):
            result = check.status()
        self.assertEqual(result["missing_packages"], ["pdfplumber"])
        self.assertTrue(result["can_install_packages"])
        self.assertFalse(result["email_ready"])
        self.assertIn("PDF bank statements", result["messages"][0])
        self.assertIn("nodejs.org", result["messages"][1])

    def test_everything_present_is_ready_with_no_messages(self):
        with mock.patch.object(check, "has_package", return_value=True), \
                mock.patch.object(check, "find_node", return_value="/usr/local/bin/node"):
            result = check.status()
        self.assertTrue(result["ready"] and result["email_ready"])
        self.assertEqual(result["messages"], [])

    def test_private_folder_packages_become_importable(self):
        packages = Path(check.private_folder()) / "lib/python3.x/site-packages"
        packages.mkdir(parents=True)
        (packages / "accounting_private_probe.py").write_text("VALUE = 7\n")
        self.addCleanup(sys.modules.pop, "accounting_private_probe", None)
        self.assertTrue(check.has_package("accounting_private_probe"))
        self.assertTrue(check.private_folder().startswith(self.home.name))

    def test_install_uses_the_private_folder_and_reports_failure_plainly(self):
        failure = subprocess.CalledProcessError(1, "pip")
        with mock.patch.object(check, "has_package", return_value=False), \
                mock.patch.object(check.subprocess, "run", side_effect=failure) as run:
            with self.assertRaises(SystemExit) as stopped:
                check.install()
        self.assertEqual(run.call_args_list[0].args[0][-1], check.private_folder())
        self.assertIn("internet connection", str(stopped.exception))

    def test_package_pins_match_requirements_file(self):
        wanted = {line.strip() for line in (ROOT / "requirements.txt").read_text().splitlines() if line.strip()}
        self.assertEqual(set(check.PACKAGES.values()), wanted)
