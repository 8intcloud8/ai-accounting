"""Xero tax rates come from the GST label, amount and accounts already in the books."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

import xero_tax as x  # noqa: E402


class XeroTaxTests(unittest.TestCase):
    def test_sales(self):
        self.assertEqual(x.rate("sale", 1000), x.GST_ON_INCOME)
        self.assertEqual(x.rate("sale", 0), x.GST_FREE_INCOME)
        self.assertEqual(x.rate("sale_refund", 100), x.GST_ON_INCOME)

    def test_purchases(self):
        self.assertEqual(x.rate("purchase", 100, accounts=["489", "820", "090"]), x.GST_ON_EXPENSES)
        self.assertEqual(x.rate("purchase", 0, accounts=["404", "090"]), x.GST_FREE_EXPENSES)

    def test_assets_take_expense_rates_as_in_simpler_bas(self):
        self.assertEqual(x.rate("purchase", 100, accounts=["720", "820", "090"]), x.GST_ON_EXPENSES)
        self.assertEqual(x.rate("purchase", 0, accounts=["710", "090"]), x.GST_FREE_EXPENSES)

    def test_off_bas_and_pending(self):
        self.assertEqual(x.rate("excluded", 0), x.BAS_EXCLUDED)
        self.assertEqual(x.rate("settlement", 500), x.BAS_EXCLUDED)
        self.assertEqual(x.rate("purchase", None, status="pending"), x.PENDING)


if __name__ == "__main__":
    unittest.main()
