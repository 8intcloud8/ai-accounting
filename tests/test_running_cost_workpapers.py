"""Tax workpaper boundaries and durable evidence, using synthetic records only."""

import copy
import tempfile
import unittest
from pathlib import Path

from accounting_store import connect
from allocation_store import allocate, save_rule
from product_store import setup
from running_cost_workpapers import calculate_fixed, list_fixed, save_fixed, CATEGORIES


class RunningCostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "accounting/db/accounting.db"
        self.evidence = self.root / "hours-and-bills.txt"
        self.evidence.write_text("Synthetic hours and expense evidence")
        setup(
            self.path,
            {
                "business_id": "example",
                "legal_name": "Example",
                "entity_type": "company",
                "gst_registered": True,
                "gst_basis": "cash",
            },
            connect,
        )
        self.request = {
            "business_id": "example",
            "claimant_id": "director",
            "claimant_type": "individual",
            "period_start": "2025-07-01",
            "period_end": "2026-06-30",
            "hours": [
                {"date": "2025-07-01", "hours": "7.5"},
                {"date": "2025-07-02", "hours": "6"},
            ],
            "hours_evidence_file": str(self.evidence),
            "actual_hours_verified": True,
            "full_year_hours_complete": True,
            "expense_evidence_verified": True,
            "work_from_home_for_income_verified": True,
            "fixed_rate": {
                "aud_per_hour": "0.70",
                "income_year_start": "2025-07-01",
                "income_year_end": "2026-06-30",
                "source_url": "https://www.ato.gov.au/example",
                "checked_on": "2026-10-15",
                "verification_note": "Synthetic test rate; not live legal verification",
                "verified_for_income_year": True,
            },
            "expenses": {
                c: {
                    "payer": "not_incurred",
                    "explanation": "Not incurred in synthetic case",
                }
                for c in CATEGORIES
            },
        }
        self.request["expenses"]["electricity"] = {
            "payer": "claimant",
            "explanation": "Unreimbursed additional working electricity",
            "reimbursement": "none",
            "unreimbursed_additional_cost_verified": True,
            "evidence_file": str(self.evidence),
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_fixed_decimal_amount_and_no_gst_or_invoice_allocation(self):
        r = save_fixed(self.path, self.request, connect)
        self.assertEqual(r["review_ready_deduction_cents"], 945)
        self.assertIsNone(r["gst_credit_cents"])
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM journals").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM running_cost_allocations").fetchone()[
                    0
                ],
                0,
            )
        self.assertTrue(
            (
                self.path.parent.parent / r["managed_evidence"][0]["relative_path"]
            ).exists()
        )

    def test_company_does_not_receive_individual_fixed_deduction(self):
        self.request["claimant_type"] = "company"
        r = calculate_fixed(self.request)
        self.assertEqual(r["status"], "inapplicable")
        self.assertIsNone(r["calculated_cents"])

    def test_all_reimbursed_inapplicable_but_some_reimbursed_can_qualify(self):
        self.request["expenses"]["electricity"] = {
            "payer": "third_party",
            "explanation": "Company pays business electricity",
        }
        self.assertEqual(calculate_fixed(self.request)["status"], "inapplicable")
        self.request["expenses"]["stationery"] = {
            "payer": "claimant",
            "explanation": "Additional unreimbursed stationery",
            "reimbursement": "none",
            "unreimbursed_additional_cost_verified": True,
            "evidence_file": str(self.evidence),
        }
        self.assertEqual(calculate_fixed(self.request)["status"], "review_ready")

    def test_unverified_rate_never_rolls_forward(self):
        self.request["fixed_rate"]["verified_for_income_year"] = False
        self.assertIsNone(calculate_fixed(self.request)["calculated_cents"])
        self.request["period_start"] = "2026-07-01"
        self.request["period_end"] = "2027-06-30"
        self.request["hours"] = [{"date": "2026-07-01", "hours": "8"}]
        with self.assertRaisesRegex(ValueError, "exact income year"):
            calculate_fixed(self.request)

    def test_interim_or_estimated_hours_never_annual_ready(self):
        self.request["period_end"] = "2025-09-30"
        r = calculate_fixed(self.request)
        self.assertEqual(r["status"], "pending")
        self.assertEqual(r["calculated_cents"], 945)
        self.assertIsNone(r["review_ready_deduction_cents"])
        self.request["period_end"] = "2026-06-30"
        self.request["actual_hours_verified"] = False
        self.assertEqual(calculate_fixed(self.request)["status"], "pending")

    def test_duplicate_hours_and_foreign_rate_source_rejected(self):
        duplicate = copy.deepcopy(self.request)
        duplicate["hours"] *= 2
        with self.assertRaisesRegex(ValueError, "unique"):
            calculate_fixed(duplicate)
        self.request["fixed_rate"]["source_url"] = "https://ato.gov.au.example.com/rate"
        with self.assertRaisesRegex(ValueError, "official HTTPS ATO"):
            calculate_fixed(self.request)

    def test_idempotent_save_and_audited_replacement(self):
        first = save_fixed(self.path, self.request, connect)
        self.assertTrue(save_fixed(self.path, self.request, connect)["already_saved"])
        replacement = copy.deepcopy(self.request)
        replacement["hours"][0]["hours"] = "8"
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            save_fixed(self.path, replacement, connect)
        replacement.update(
            supersedes_id=first["workpaper_id"],
            correction_reason="Corrected hours from diary",
        )
        second = save_fixed(self.path, replacement, connect)
        rows = list_fixed(self.path, "example")["workpapers"]
        self.assertTrue(rows[0]["superseded"])
        self.assertFalse(rows[1]["superseded"])
        self.assertEqual(second["calculated_cents"], 980)
        self.assertEqual(first["calculated_cents"], 945)

    def test_evidence_retained_after_original_removed_and_new_csv_only(self):
        r = save_fixed(self.path, self.request, connect)
        self.evidence.unlink()
        target = self.root / "workpapers.csv"
        list_fixed(self.path, "example", target)
        self.assertIn("945", target.read_text())
        with self.assertRaises(FileExistsError):
            list_fixed(self.path, "example", target)
        self.assertTrue(
            (
                self.path.parent.parent / r["managed_evidence"][0]["relative_path"]
            ).exists()
        )

    def test_metered_electricity_apportions_energy_and_rejects_duplicate_methods(self):
        save_rule(
            self.path,
            {
                "business_id": "example",
                "supplier_key": "energy",
                "category": "electricity",
                "effective_from": "2026-07-01",
                "evidence_status": "supported",
                "provenance": "Synthetic meter evidence",
                "method": "electricity_actual",
            },
            connect,
        )
        request = {
            "business_id": "example",
            "supplier_key": "energy",
            "category": "electricity",
            "period_start": "2026-07-01",
            "period_end": "2026-09-30",
            "usage_supported": True,
            "segments": [
                {
                    "appliance_id": "office",
                    "start": "2026-07-01",
                    "end": "2026-09-30",
                    "metered_kwh": "100.5",
                    "rate_per_kwh": "0.35",
                    "business_percent": "80",
                    "evidence": "Synthetic submeter and tariff",
                }
            ],
        }
        r = allocate(self.path, request, connect)
        self.assertEqual(r["business_cents"], 2814)
        self.assertIsNone(r["gst_credit_cents"])
        request["segments"][0]["hours"] = "10"
        with self.assertRaisesRegex(ValueError, "not both"):
            allocate(self.path, request, connect)

    def test_paid_then_fully_reimbursed_is_not_eligible(self):
        self.request["expenses"]["electricity"]["reimbursement"] = "full"
        self.assertEqual(calculate_fixed(self.request)["status"], "inapplicable")
        self.request["expenses"]["electricity"]["reimbursement"] = "unknown"
        self.assertEqual(calculate_fixed(self.request)["status"], "pending")

    def test_annual_consolidates_quarters_without_double_counting(self):
        quarter = copy.deepcopy(self.request)
        quarter["period_end"] = "2025-09-30"
        first = save_fixed(self.path, quarter, connect)
        second_quarter = copy.deepcopy(self.request)
        second_quarter.update(period_start="2025-10-01", period_end="2025-12-31")
        second_quarter["hours"] = [{"date": "2025-10-02", "hours": "8"}]
        second = save_fixed(self.path, second_quarter, connect)
        annual = copy.deepcopy(self.request)
        annual["hours"] += second_quarter["hours"]
        annual.update(
            supersedes_ids=[first["workpaper_id"], second["workpaper_id"]],
            correction_reason="Consolidate full-year diary",
        )
        result = save_fixed(self.path, annual, connect)
        self.assertEqual(result["review_ready_deduction_cents"], 1505)
        current = [
            r
            for r in list_fixed(self.path, "example")["workpapers"]
            if not r["superseded"]
        ]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["workpaper_id"], result["workpaper_id"])

    def test_superseded_replay_cannot_present_current_deduction(self):
        first = save_fixed(self.path, self.request, connect)
        changed = copy.deepcopy(self.request)
        changed.update(
            supersedes_id=first["workpaper_id"], correction_reason="Hours corrected"
        )
        changed["hours"][0]["hours"] = "8"
        latest = save_fixed(self.path, changed, connect)
        old = save_fixed(self.path, self.request, connect)
        self.assertEqual(old["status"], "superseded")
        self.assertIsNone(old["review_ready_deduction_cents"])
        self.assertEqual(old["replacement_id"], latest["workpaper_id"])

    def test_tampered_evidence_removes_readiness_on_list_and_replay(self):
        saved = save_fixed(self.path, self.request, connect)
        managed = (
            self.path.parent.parent / saved["managed_evidence"][0]["relative_path"]
        )
        managed.write_text("changed")
        for result in (
            list_fixed(self.path, "example")["workpapers"][0],
            save_fixed(self.path, self.request, connect),
        ):
            self.assertEqual(result["status"], "pending")
            self.assertIsNone(result["review_ready_deduction_cents"])

    def test_different_business_cannot_save(self):
        self.request["business_id"] = "other"
        with self.assertRaisesRegex(ValueError, "Configure this business"):
            save_fixed(self.path, self.request, connect)


if __name__ == "__main__":
    unittest.main()
