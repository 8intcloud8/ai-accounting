"""The period's master workbook: one file, rewritten after every change, where every
number on the dashboard can be checked.

BAS: the figures as Excel formulas over the GST items sheet, then what is next.
GST items: every Business or Shared GST line (Personal left out), counted or pending, with its G1, 1A and 1B amounts.
Transactions and By payee: every bank transaction and where it stands.
Reads the books only.
"""

from contextlib import closing
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

import bas_dashboard
import chart
import proposal_store
import transaction_purpose
import workbook_style as style
from proposal_store import cell

GST_HEADERS = ["Date", "Reference", "Description", "Treatment", "Status", "Gross", "GST",
               "G1", "1A", "1B", "How to resolve", "ATO source"]
TREATMENT = {"sale": "Sale", "sale_refund": "Sale refund", "purchase": "Purchase",
             "purchase_refund": "Purchase refund", "excluded": "No GST", "settlement": "GST payment"}
# Columns of GST_HEADERS the BAS formulas add up.
SUM_COLUMN = {"G1": "H", "1A": "I", "1B": "J"}


def personal(db, journal_id, transaction_id, purposes):
    """True when the line is Personal, by the same rule as the Purpose column of Transactions."""
    if transaction_id in purposes:
        return purposes[transaction_id]["purpose"] == "Personal"
    code = next((c for (c,) in db.execute(
        "SELECT account_code FROM journal_lines WHERE journal_id=? ORDER BY line_no", (journal_id,))
        if chart.current(c) not in proposal_store.CONTROL_ACCOUNTS), "")
    return bool(code) and chart.current(code) in chart.OWNER_ACCOUNTS


def gst_rows(db, start, end):
    """Every Business or Shared GST line in the period that is not reversed, counted or pending,
    in dollars. Personal lines are left out unless they carry a counted BAS amount."""
    purposes = transaction_purpose.reviewed(db)
    rows = []
    for r in db.execute(
            "SELECT g.attribution_date,j.reference,j.description,g.label,g.status,g.gross_cents,g.gst_cents,"
            "res.resolve,s.url,s.note,j.id,j.transaction_id FROM gst_items g JOIN journals j ON j.id=g.journal_id "
            "LEFT JOIN gst_resolutions res ON res.journal_id=g.journal_id "
            "LEFT JOIN gst_sources s ON s.journal_id=g.journal_id "
            "WHERE g.attribution_date BETWEEN ? AND ? "
            "AND NOT EXISTS(SELECT 1 FROM journals x WHERE x.reverses_id=j.id) "
            "ORDER BY g.attribution_date,j.id", (start, end)):
        day, ref, text, label, status, gross, gst, resolve, url, note, jid, tid = r
        counted = status == "reviewed"
        sign = -1 if label.endswith("_refund") else 1
        sale, purchase = label in ("sale", "sale_refund"), label in ("purchase", "purchase_refund")
        # Never drop a counted BAS amount: the sheet must still add up to the BAS figures.
        if personal(db, jid, tid, purposes) and not (counted and (sale or purchase)):
            continue
        rows.append([cell(v) for v in (
            day, ref, text, TREATMENT.get(label, label), "Counted" if counted else "Pending",
            gross / 100, (gst or 0) / 100,
            sign * gross / 100 if counted and sale else None,
            sign * (gst or 0) / 100 if counted and sale else None,
            sign * (gst or 0) / 100 if counted and purchase else None,
            "" if counted else (resolve or "Check the evidence, then mark the GST reviewed or excluded"),
            url or note or "")])
    return rows


def bas_sheet(book, data, gst):
    sheet = book.create_sheet("BAS", 0)
    sheet.sheet_view.showGridLines = False
    sheet["A1"] = data["business"]
    sheet["A1"].font = Font(size=16, bold=True, color=style.INK)
    sheet["A2"] = f"BAS {data['start']} to {data['end']} · due {data['due']} · {data['basis']} basis"
    sheet["A2"].font = Font(color="5D6B78")
    sheet.append([])
    sheet.append(["Label", "What it is", "Amount", "Where it comes from"])
    for box in sheet[4]:
        box.font = Font(bold=True)
    payg = data.get("payg") or {"W3": 0, "W4": 0}
    rows = {}

    def add(label, what, formula, source, bold=False):
        sheet.append([label, what, formula, source])
        row = sheet.max_row
        rows[label] = f"C{row}"
        sheet.cell(row, 1).font = Font(bold=True)
        sheet.cell(row, 3).number_format = style.MONEY
        if bold:
            sheet.cell(row, 3).font = Font(bold=True, size=13)

    # Plain numbers, not formulas: previewers (Quick Look, mail) show formulas as blank.
    amount = {k: data["labels"].get(k, 0) for k in ("G1", "1A", "1B", "W1", "W2", "W5", "4", "8A", "8B", "9")}
    for label, what in (("G1", "Total sales, including GST"), ("1A", "GST on sales"), ("1B", "GST on purchases")):
        add(label, what, amount[label],
            f"Column {label} of the GST items sheet: counted lines only, whole dollars")
    add("W1", "Total wages paid", amount["W1"], "Gross column of the PAYG withholding sheet")
    add("W2", "Tax withheld from wages", amount["W2"], "Withheld column of the PAYG withholding sheet")
    add("W3", "Other amounts withheld", payg["W3"], "Saved with the pay runs")
    add("W4", "Withheld where no ABN quoted", payg["W4"], "Saved with the pay runs")
    add("W5", "Total amounts withheld", amount["W5"], "W2 + W3 + W4")
    add("4", "PAYG tax withheld", amount["4"], "Same as W5")
    add("8A", "Amounts you owe", amount["8A"], "1A + 4")
    add("8B", "Amounts the ATO owes you", amount["8B"], "1B")
    add("9", "Amount to pay (a minus amount is a refund)", amount["9"], "8A - 8B", bold=True)
    sheet.append([])
    pending = [r for r in gst if r[4] == "Pending"]
    line = sheet.max_row + 1
    if pending:
        sheet.cell(line, 1, f"Not counted yet: {len(pending)} pending GST line{'s' if len(pending) != 1 else ''}, "
                            f"${sum(r[6] for r in pending):,.2f} GST. See Status = Pending on the GST items sheet.")
        sheet.cell(line, 1).font = Font(color="8A5300", bold=True)
        line += 2
    sheet.cell(line, 1, "Next").font = Font(bold=True)
    upcoming = data["next"]["question"].removeprefix("Shall I ").removesuffix("?").removesuffix(" now")
    sheet.cell(line, 2, upcoming[:1].upper() + upcoming[1:])
    line += 1
    todo = list(dict.fromkeys(data["todo"]))
    sheet.cell(line, 1, "Still to do").font = Font(bold=True)
    for item in todo or ["Nothing left: ready for the BAS draft"]:
        sheet.cell(line, 2, cell(item))
        line += 1
    sheet.cell(line + 1, 1, f"Updated {data['read_at'][:16].replace('T', ' ')}. This file is rewritten after every change.")
    sheet.cell(line + 1, 1).font = Font(italic=True, color="8A97A3")
    for column, width in zip("ABCD", (12, 42, 16, 60)):
        sheet.column_dimensions[column].width = width
    for row in sheet.iter_rows(min_row=18):
        for box in row:
            box.alignment = Alignment(wrap_text=False, vertical="top")
    return sheet


def payg_sheet(book, runs):
    sheet = book.create_sheet("PAYG withholding")
    sheet.append(["Pay date", "Gross (W1)", "Withheld (W2)", "Net paid", "Evidence"])
    for run in runs:
        sheet.append([cell(v) for v in (run.get("pay_date"), run["gross_cents"] / 100, run["withheld_cents"] / 100,
                                         run["net_cents"] / 100, run.get("evidence", ""))])
    style.as_table(sheet, "PaygRuns", money=("Gross (W1)", "Withheld (W2)", "Net paid"), wrap=("Evidence",),
                   widths={"Pay date": 12, "Gross (W1)": 14, "Withheld (W2)": 15, "Net paid": 13, "Evidence": 60})


def payg_runs(db, start, end):
    import json

    row = db.execute("SELECT payload_json FROM payg_withholding WHERE start=? AND end=?", (start, end)).fetchone()
    if row is None:
        return [], {"W3": 0, "W4": 0}
    saved = json.loads(row[0])
    return saved.get("runs", []), {"W3": int(saved.get("w3_cents", 0) / 100), "W4": int(saved.get("w4_cents", 0) / 100)}


def gst_sheet(book, gst):
    sheet = book.create_sheet("GST items")
    sheet.append(GST_HEADERS)
    for row in gst:
        sheet.append(row)
    letter = style.as_table(sheet, "GSTItems", money=("Gross", "GST", "G1", "1A", "1B"),
                            wrap=("How to resolve",), widths={
                                "Date": 12, "Reference": 16, "Description": 40, "Treatment": 15, "Status": 11,
                                "Gross": 13, "GST": 11, "G1": 13, "1A": 11, "1B": 11, "How to resolve": 44,
                                "ATO source": 40})
    style.colour_status(sheet, letter["Status"], sheet.max_row)


def build(db_path, start, end, output):
    """Write the master workbook for the period to `output` and return its path."""
    data = bas_dashboard.snapshot(db_path, start, end)
    with closing(bas_dashboard.read_only(db_path)) as db:
        gst = gst_rows(db, start, end)
        runs, data["payg"] = payg_runs(db, start, end)
        transactions = proposal_store.transaction_rows(db, start, end)
    book = Workbook()
    book.remove(book.active)
    bas_sheet(book, data, gst)
    gst_sheet(book, gst)
    payg_sheet(book, runs)
    proposal_store.transaction_sheets(book, transactions, "By payee", payee_last=True)
    book.active = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)
    return output


if __name__ == "__main__":  # pragma: no cover - manual check
    import sys
    from pathlib import Path

    print(build(Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])), date.today())
