"""Tax return labels for the year: which return label each account's total goes to.

Sole traders: Business and professional items schedule 2026, item P8 (income and expenses).
Companies: Company tax return 2026, item 6 (calculation of total profit or loss).
Both come from the official 2026 instructions in the ATO library (see SOURCES).

The amounts are the books' business share: private use is already in Owner Drawings and
GST credits are already out of the expenses (input tax credits reduce deductions). Some
accounts need a person to decide before the return (marked `check`), for example
entertainment, which is mostly not deductible, and consultants, who go at the
Contractor label while accountants and lawyers go at All other expenses.

Trusts and partnerships use other returns; their accounts are listed without labels.
"""

from contextlib import closing

import reports

SOURCES = {
    "sole_trader": "Business and professional items schedule instructions 2026, P8 (pp. 43-56); "
                   "https://www.ato.gov.au/forms-and-instructions/business-and-professional-items-schedule-2026-instructions",
    "company": "Company tax return instructions 2026, item 6 (pp. 78-103); "
               "https://www.ato.gov.au/forms-and-instructions/company-tax-return-2026-instructions",
}

# code -> (sole trader P8 label, company item 6 label, check note or "")
LABELS = {
    "200": ("Other business income", "C Other sales of goods and services", ""),
    "260": ("Other business income", "R Other gross income", ""),
    "270": ("Not business income: individual return item 10 Gross interest", "F Gross interest",
            "Sole trader: interest on a business account is usually declared as interest, not at P8; confirm"),
    "310": ("Purchases and other costs (Cost of sales)", "A Cost of sales",
            "Cost of sales also needs opening and closing stock if you hold trading stock"),
    "400": ("P All other expenses", "S All other expenses", ""),
    "404": ("P All other expenses", "S All other expenses", ""),
    "408": ("P All other expenses", "S All other expenses", ""),
    "412": ("P All other expenses", "S All other expenses",
            "Accounting and legal go here; payments to consultants or contractors go at the Contractor label"),
    "416": ("Depreciation expenses", "X Depreciation expenses",
            "Use the tax depreciation (simplified rules or instant asset write-off), not book depreciation"),
    "420": ("P All other expenses", "S All other expenses",
            "Entertainment is mostly not deductible: add it back as a reconciliation adjustment "
            "(P8 expense reconciliation; company item 7); confirm any deductible part"),
    "425": ("P All other expenses", "S All other expenses", ""),
    "429": ("P All other expenses", "S All other expenses", ""),
    "433": ("P All other expenses", "S All other expenses", ""),
    "437": ("Q Interest expenses within Australia", "V Interest expenses within Australia", ""),
    "441": ("P All other expenses", "S All other expenses", ""),
    "445": ("P All other expenses", "S All other expenses", ""),
    "449": ("N Motor vehicle expenses", "Y Motor vehicle expenses",
            "Sole trader car: claim by cents per km or logbook; depreciation and interest go at their own labels"),
    "453": ("P All other expenses", "S All other expenses", ""),
    "461": ("P All other expenses", "S All other expenses", ""),
    "469": ("K Rent expenses", "H Rent expenses", ""),
    "473": ("O Repairs and maintenance", "Z Repairs and maintenance", ""),
    "477": ("P All other expenses (also P15 G Total salary and wage expenses)",
            "S All other expenses (also item 8 D Total salary and wage expenses)", ""),
    "478": ("G Superannuation expenses", "D Superannuation expenses",
            "Only super for employees goes here; check whether any is for the owner"),
    "485": ("P All other expenses", "S All other expenses", ""),
    "489": ("P All other expenses", "S All other expenses", ""),
    "493": ("P All other expenses", "S All other expenses", ""),
    "494": ("P All other expenses", "S All other expenses", ""),
}
ADD_BACK = ("420",)  # in the expenses as booked, added back before taxable income


def summary(db, start, end, entity_type):
    """Label totals for the year, the accounts behind each, and what still needs a decision."""
    sections, net = reports.profit_and_loss(db, start, end)
    column = {"sole_trader": 0, "company": 1}.get(entity_type)
    by_label, accounts, checks = {}, [], []
    for kind, lines in sections:
        for code, name, cents in lines:
            known = LABELS.get(code)
            label = (known[column] if known and column is not None
                     else "Ask the accountant: no label for this account" if column is not None
                     else "Not mapped for this entity type")
            note = known[2] if known else ""
            accounts.append({"code": code, "name": name, "kind": kind, "cents": cents, "label": label, "check": note})
            entry = by_label.setdefault(label, {"label": label, "kind": kind, "cents": 0, "accounts": []})
            entry["cents"] += cents
            entry["accounts"].append(f"{code} {name}")
            if note:
                checks.append(f"{code} {name}: {note}")
    income = sum(a["cents"] for a in accounts if a["kind"] == "income" and not a["label"].startswith("Not business"))
    expenses = sum(a["cents"] for a in accounts if a["kind"] == "expense")
    add_back = sum(a["cents"] for a in accounts if a["code"] in ADD_BACK)
    return {"entity_type": entity_type, "source": SOURCES.get(entity_type),
            "labels": sorted(by_label.values(), key=lambda e: (e["kind"] != "income", e["label"])),
            "accounts": accounts, "checks": checks,
            "total_business_income_cents": income, "total_expenses_cents": expenses,
            "net_cents": income - expenses, "book_profit_cents": net, "add_back_cents": add_back,
            "note": "Draft from the books for you or your accountant to check; not a lodged return",
            "warning": ("Labels follow the 2026 instructions; check the instructions for this year's return"
                        if end > "2026-06-30" else None)}


def workbook(db, start, end, entity_type, output):
    """Excel file: the labels to copy into the return, then the accounts behind them."""
    from openpyxl import Workbook

    import workbook_style as style

    data = summary(db, start, end, entity_type)
    book = Workbook()
    book.remove(book.active)
    sheet = book.create_sheet("Tax return labels")
    sheet.append(["Label", "Amount", "From accounts"])
    for e in data["labels"]:
        sheet.append([e["label"], e["cents"] / 100, ", ".join(e["accounts"])])
    style.as_table(sheet, "TaxLabels", money=("Amount",), wrap=("From accounts",),
                   widths={"Label": 56, "Amount": 15, "From accounts": 60})
    detail = book.create_sheet("By account")
    detail.append(["Code", "Account", "Amount", "Label", "Check before lodging"])
    for a in data["accounts"]:
        detail.append([a["code"], a["name"], a["cents"] / 100, a["label"], a["check"]])
    style.as_table(detail, "TaxAccounts", money=("Amount",), wrap=("Check before lodging",),
                   widths={"Code": 8, "Account": 30, "Amount": 14, "Label": 52, "Check before lodging": 60})
    title = {"sole_trader": "Sole trader: business schedule P8", "company": "Company return item 6"}
    style.overview(book, title.get(entity_type, "Tax return labels"), f"{start} to {end} · {data['note']}", [
        ("Business income", data["total_business_income_cents"] / 100, True),
        ("Total expenses", data["total_expenses_cents"] / 100, True),
        ("Net business income", data["net_cents"] / 100, True),
        ("Likely add-back (entertainment)", data["add_back_cents"] / 100, True),
        ("Items to check", len(data["checks"]), False)])
    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)
    return dict(data, workbook=str(output))




def from_path(path, start, end, entity_type, output, connect):
    with closing(connect(path)) as db:
        return workbook(db, start, end, entity_type, output)
