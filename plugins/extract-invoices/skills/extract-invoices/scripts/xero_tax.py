"""Xero's Australian tax rates, worked out from what the books already hold.

A coded line carries a GST label (sale, purchase, refunds, excluded, settlement), its
GST amount and its accounts. That is enough to name the Xero tax rate an accountant
expects to see, and the Xero code a later push to Xero needs. Input Taxed and GST on
Imports cannot be told apart from these facts, so they are never guessed.

Xero's Australian organisations now report Simpler BAS (G1, 1A, 1B), and new ones have
GST on Capital and GST Free Capital archived: an asset purchase takes GST on Expenses or
GST Free Expenses, the same as this engine's BAS.
"""

# (name shown in Xero, Xero API TaxType)
GST_ON_INCOME = ("GST on Income", "OUTPUT")
GST_FREE_INCOME = ("GST Free Income", "EXEMPTOUTPUT")
GST_ON_EXPENSES = ("GST on Expenses", "INPUT")
GST_FREE_EXPENSES = ("GST Free Expenses", "EXEMPTEXPENSES")
BAS_EXCLUDED = ("BAS Excluded", "BASEXCLUDED")
PENDING = ("Not decided yet", "")


def rate(label, gst_cents, status="reviewed", accounts=()):
    """The (name, TaxType) for one GST item. Pending items have no rate yet. `accounts` is
    accepted for callers that pass the journal's lines; the rate does not depend on them."""
    if status != "reviewed":
        return PENDING
    has_gst = bool(gst_cents)
    if label in ("sale", "sale_refund"):
        return GST_ON_INCOME if has_gst else GST_FREE_INCOME
    if label in ("purchase", "purchase_refund"):
        return GST_ON_EXPENSES if has_gst else GST_FREE_EXPENSES
    return BAS_EXCLUDED  # excluded movements and GST settlements stay off the BAS
