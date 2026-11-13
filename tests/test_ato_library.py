"""Local ATO library: add guides, search offline, and accept only exact quotes."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "accounting_core"))
import ato_library  # noqa: E402

GUIDE = """# Tax invoices

You need a tax invoice to claim a GST credit for purchases that cost more than $82.50
(including GST). If the total is $1,000 or more, the tax invoice must also show the
buyer's identity or ABN.

# Input-taxed sales

Financial supplies and residential rent are input-taxed. You cannot claim GST credits
for purchases that relate to making input-taxed sales.
"""


def tiny_pdf(pages):
    """A minimal text PDF, one string per page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None,
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {len(objs)} 0 R >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.lib = Path(tempfile.mkdtemp())
        self.old = os.environ.get("AI_ACCOUNTING_LIBRARY")
        os.environ["AI_ACCOUNTING_LIBRARY"] = str(self.lib)
        self.src = Path(tempfile.mkdtemp())
        (self.src / "gst_guide.md").write_text(GUIDE)
        self.added = ato_library.add(self.src / "gst_guide.md", title="GST guide",
                                     url="https://www.ato.gov.au/gst", issued="2026-07-01")

    def tearDown(self):
        os.environ["AI_ACCOUNTING_LIBRARY"] = self.old or ""
        shutil.rmtree(self.lib, ignore_errors=True)
        shutil.rmtree(self.src, ignore_errors=True)

    def test_search_finds_passage_with_heading_and_page(self):
        hits = ato_library.search("tax invoice 82.50")["results"]
        self.assertEqual("GST guide", hits[0]["guide"])
        self.assertEqual("Tax invoices", hits[0]["heading"])
        self.assertEqual(1, hits[0]["page"])
        self.assertTrue((self.lib / "gst_guide.md").exists())
        self.assertEqual(["GST guide"], [g["title"] for g in ato_library.guides()["guides"]])
        self.assertIn("82.50", hits[0]["passage"])
        top = ato_library.search('"input-taxed"')["results"][0]
        self.assertEqual("Input-taxed sales", top["heading"])

    def test_empty_search_and_unknown_topic(self):
        self.assertEqual([], ato_library.search("fuel tax credits")["results"])
        with self.assertRaises(ValueError):
            ato_library.search("  ")

    def test_quote_must_match_page_word_for_word(self):
        cite = {"sha256": self.added["sha256"], "page": 1,
                "quote": "You need a tax invoice to claim a GST credit for purchases that cost more than $82.50"}
        ok = ato_library.verify_quote(cite)
        self.assertEqual("GST guide", ok["title"])
        for bad in (dict(cite, quote="You need a tax invoice for purchases over $50 to claim GST"),
                    dict(cite, page=2), dict(cite, quote="short"), dict(cite, sha256="abc")):
            with self.assertRaises(ValueError):
                ato_library.verify_quote(bad)

    def test_stale_and_out_of_period_warnings(self):
        old = self.src / "old.txt"
        old.write_text("Old guidance about GST registration thresholds for small businesses.")
        ato_library.add(old, issued="2020-01-01", applies_to="2021-06-30")
        hit = ato_library.search("registration thresholds", period_end="2026-09-30")["results"][0]
        self.assertTrue(any("over 12 months" in w for w in hit["warnings"]))
        self.assertTrue(any("applies only to 2021-06-30" in w for w in hit["warnings"]))
        self.assertTrue(any("no ATO source address" in w for w in hit["warnings"]))

    def test_sync_indexes_dropped_files_once(self):
        (self.lib / "rent.html").write_text(
            "<html><nav>menu</nav><h2>Commercial rent</h2><p>Commercial rent is a taxable supply.</p></html>")
        first = ato_library.sync()
        self.assertEqual(["rent"], [g["title"] for g in first["added"]])
        self.assertEqual([], ato_library.sync()["added"])
        hit = ato_library.search("commercial rent")["results"][0]
        self.assertEqual("Commercial rent", hit["heading"])
        self.assertNotIn("menu", hit["passage"])

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_pdf_pages_are_cited_by_page_number(self):
        pdf = self.src / "bas_guide.pdf"
        pdf.write_bytes(tiny_pdf(["Label G1 is total sales including GST.",
                                  "Label 1B is GST on purchases you can claim."]))
        added = ato_library.add(pdf, title="BAS guide")
        self.assertEqual(2, added["pages"])
        hit = ato_library.search("GST purchases claim")["results"][0]
        self.assertEqual(("BAS guide", 2), (hit["guide"], hit["page"]))
        ato_library.verify_quote({"sha256": added["sha256"], "page": 2,
                                  "quote": "Label 1B is GST on purchases you can claim"})

    def test_cli_needs_no_workspace(self):
        env = {k: v for k, v in os.environ.items() if k != "AI_ACCOUNTING_DB"}
        env["AI_ACCOUNTING_LIBRARY"] = str(self.lib)
        out = subprocess.run([sys.executable, str(ROOT / "accounting_core/accounting_store.py"),
                              "ato-search", "tax invoice"], capture_output=True, text=True, env=env, check=True)
        self.assertEqual("Tax invoices", json.loads(out.stdout)["results"][0]["heading"])

    def test_bundled_copy_works_without_original_files(self):
        """Plugins ship only library.json; search and quote checks must not need the PDFs."""
        for f in self.lib.iterdir():
            if f.name != "library.json":
                f.unlink()
        self.assertEqual("Tax invoices", ato_library.search("tax invoice")["results"][0]["heading"])
        ato_library.verify_quote({"sha256": self.added["sha256"], "page": 1,
                                  "quote": "You need a tax invoice to claim a GST credit"})
        self.assertEqual([], ato_library.sync()["added"])
