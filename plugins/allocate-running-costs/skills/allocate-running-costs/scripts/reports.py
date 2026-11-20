"""Xero's standard reports from the journal lines: Profit and Loss, Balance Sheet,
Trial Balance and the GST Audit Report.

Every figure is a sum of posted journal lines. A reversal is a journal of opposite lines
on the same date, so summing everything already leaves reversed work out. Australian
financial years start on 1 July; the Balance Sheet splits earnings the way Xero does,
into this year's (Current Year Earnings) and earlier years' (Retained Earnings).
"""

from datetime import date

import workbook_style as style
from openpyxl.styles import Font

CREDIT_NORMAL = ("liability", "equity", "income")
SECTIONS = {"income": "Income", "expense": "Less Operating Expenses", "asset": "Assets",
            "liability": "Liabilities", "equity": "Equity"}
BOLD = Font(bold=True)


def year_start(day):
    """1 July of the Australian financial year that `day` (YYYY-MM-DD) falls in."""
    d = date.fromisoformat(day)
    return date(d.year if d.month >= 7 else d.year - 1, 7, 1).isoformat()


def balances(db, end, start=None):
    """{code: (name, kind, balance)} with the balance in the account's normal direction."""
    where, args = "j.date <= ?", [end]
    if start:
        where, args = "j.date BETWEEN ? AND ?", [start, end]
    rows = db.execute(
        "SELECT a.code,a.name,a.kind,COALESCE(SUM(l.debit_cents-l.credit_cents),0) FROM ledger_accounts a "
        "JOIN journal_lines l ON l.account_code=a.code JOIN journals j ON j.id=l.journal_id "
        f"WHERE {where} GROUP BY a.code ORDER BY a.code", args)
    return {code: (name, kind, -net if kind in CREDIT_NORMAL else net) for code, name, kind, net in rows}


def earnings(db, end, start=None):
    """Income less expenses, in cents."""
    found = balances(db, end, start)
    return (sum(b for _, k, b in found.values() if k == "income")
            - sum(b for _, k, b in found.values() if k == "expense"))


def profit_and_loss(db, start, end):
    """[(section, [(code, name, cents)])] plus net profit."""
    found = balances(db, end, start)
    sections = [(kind, [(c, n, b) for c, (n, k, b) in found.items() if k == kind and b])
                for kind in ("income", "expense")]
    return sections, earnings(db, end, start)


def balance_sheet(db, end):
    """[(section, [(code, name, cents)])]; equity includes this year's and earlier earnings."""
    found = balances(db, end)
    begin = year_start(end)
    current = earnings(db, end, begin)
    before = earnings(db, date.fromordinal(date.fromisoformat(begin).toordinal() - 1).isoformat())
    sections = [(kind, [(c, n, b) for c, (n, k, b) in found.items() if k == kind and b])
                for kind in ("asset", "liability", "equity")]
    equity = sections[2][1]
    if before:
        equity.append(("", "Retained Earnings (earlier years)", before))
    if current:
        equity.append(("", "Current Year Earnings", current))
    return sections


def trial_balance(db, end):
    """[(code, name, debit_cents, credit_cents)] for every account with a balance."""
    rows = db.execute(
        "SELECT a.code,a.name,SUM(l.debit_cents-l.credit_cents) FROM ledger_accounts a "
        "JOIN journal_lines l ON l.account_code=a.code JOIN journals j ON j.id=l.journal_id "
        "WHERE j.date <= ? GROUP BY a.code HAVING SUM(l.debit_cents-l.credit_cents) != 0 ORDER BY a.code", (end,))
    return [(c, n, net if net > 0 else 0, -net if net < 0 else 0) for c, n, net in rows]


def _title(sheet, title, subtitle):
    sheet["A1"] = title
    sheet["A1"].font = Font(size=14, bold=True)
    sheet["A2"] = subtitle
    sheet["A2"].font = Font(color="5D6B78")
    sheet.append([])
    sheet.sheet_view.showGridLines = False
    sheet.column_dimensions["A"].width = 8
    sheet.column_dimensions["B"].width = 38


def _money(sheet, row, column):
    sheet.cell(row, column).number_format = style.MONEY


def _section(sheet, label, lines, total_label):
    sheet.append([SECTIONS[label]])
    sheet.cell(sheet.max_row, 1).font = BOLD
    for code, name, cents in lines:
        sheet.append([code, name, cents / 100])
        _money(sheet, sheet.max_row, 3)
    total = sum(c for _, _, c in lines)
    sheet.append(["", total_label, total / 100])
    sheet.cell(sheet.max_row, 2).font = BOLD
    sheet.cell(sheet.max_row, 3).font = BOLD
    _money(sheet, sheet.max_row, 3)
    sheet.append([])
    return total


def pnl_sheet(book, db, start, end):
    sheet = book.create_sheet("Profit and Loss")
    _title(sheet, "Profit and Loss", f"{start} to {end}")
    sections, net = profit_and_loss(db, start, end)
    for kind, lines in sections:
        _section(sheet, kind, lines, "Total " + ("Income" if kind == "income" else "Operating Expenses"))
    sheet.append(["", "Net Profit", net / 100])
    for column in (2, 3):
        sheet.cell(sheet.max_row, column).font = Font(bold=True, size=12)
    _money(sheet, sheet.max_row, 3)
    sheet.column_dimensions["C"].width = 16
    return net


def balance_sheet_sheet(book, db, end):
    sheet = book.create_sheet("Balance Sheet")
    _title(sheet, "Balance Sheet", f"As at {end}")
    totals = {kind: _section(sheet, kind, lines, "Total " + SECTIONS[kind])
              for kind, lines in balance_sheet(db, end)}
    sheet.append(["", "Net Assets", (totals["asset"] - totals["liability"]) / 100])
    sheet.cell(sheet.max_row, 2).font = Font(bold=True, size=12)
    _money(sheet, sheet.max_row, 3)
    sheet.column_dimensions["C"].width = 16
    return totals


def trial_balance_sheet(book, db, end):
    sheet = book.create_sheet("Trial Balance")
    sheet.append(["Code", "Account", "Debit", "Credit"])
    rows = trial_balance(db, end)
    for code, name, debit, credit in rows:
        sheet.append([code, name, debit / 100 or None, credit / 100 or None])
    style.as_table(sheet, "TrialBalance", money=("Debit", "Credit"),
                   widths={"Code": 8, "Account": 38, "Debit": 15, "Credit": 15})
    sheet.append(["", "Total", sum(r[2] for r in rows) / 100, sum(r[3] for r in rows) / 100])
    for column in (2, 3, 4):
        sheet.cell(sheet.max_row, column).font = BOLD
    for column in (3, 4):
        _money(sheet, sheet.max_row, column)
    return rows


def gst_audit_sheet(book, gst, headers):
    """Xero's GST Audit Report: the period's GST lines grouped by tax rate, with subtotals."""
    at = {h: headers.index(h) for h in ("Date", "Reference", "Description", "Xero tax rate", "Status", "Gross", "GST")}
    sheet = book.create_sheet("GST Audit")
    _title(sheet, "GST Audit Report", "Every GST line of the period, grouped by Xero tax rate")
    sheet.append(["Date", "Reference", "Description", "Status", "Gross", "GST", "Net"])
    for box in sheet[sheet.max_row]:
        box.font = BOLD
    by_rate = {}
    for row in gst:
        by_rate.setdefault(row[at["Xero tax rate"]], []).append(row)
    for rate in sorted(by_rate):
        sheet.append([rate])
        sheet.cell(sheet.max_row, 1).font = BOLD
        gross = tax = 0
        for row in by_rate[rate]:
            g, t = row[at["Gross"]] or 0, row[at["GST"]] or 0
            gross, tax = gross + g, tax + t
            sheet.append([row[at["Date"]], row[at["Reference"]], row[at["Description"]], row[at["Status"]],
                          g, t, round(g - t, 2)])
            for column in (5, 6, 7):
                _money(sheet, sheet.max_row, column)
        sheet.append(["", "", "Total " + rate, "", round(gross, 2), round(tax, 2), round(gross - tax, 2)])
        for column in (3, 5, 6, 7):
            sheet.cell(sheet.max_row, column).font = BOLD
        for column in (5, 6, 7):
            _money(sheet, sheet.max_row, column)
        sheet.append([])
    for column, width in zip("ABCDEFG", (12, 18, 40, 11, 14, 12, 14)):
        sheet.column_dimensions[column].width = width
