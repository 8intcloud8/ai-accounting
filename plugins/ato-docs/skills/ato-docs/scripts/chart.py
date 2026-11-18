"""The built-in chart of accounts, modelled on Xero's Australian default chart.

Every account code the engine treats specially is named here, so the chart lives in one
place. Codes follow Xero's AU numbering: 0xx bank, 2xx revenue, 3xx direct costs, 4xx
expenses, 6xx/7xx assets, 8xx liabilities and owner accounts, 9xx loans and equity.

Like Xero, there is one GST control account (820). BAS figures come from gst_items, never
from account balances, so purchase and sales GST need no separate accounts.
"""

import json

VERSION = 6  # PRAGMA user_version once the database uses this chart

BANK = "090"
SALES = "200"
OTHER_REVENUE = "260"
INTEREST_INCOME = "270"
GENERAL_EXPENSES = "429"
RECEIVABLES = "610"
EQUIPMENT = "710"
PAYABLES = "800"
GST = "820"
DRAWINGS = "880"
FUNDS_INTRODUCED = "881"
LOAN = "900"

# (code, name, kind). kind is the engine's ledger class, not Xero's finer account type.
CHART = [
    (BANK, "Business Bank Account", "asset"),
    (SALES, "Sales", "income"),
    (OTHER_REVENUE, "Other Revenue", "income"),
    (INTEREST_INCOME, "Interest Income", "income"),
    ("310", "Cost of Goods Sold", "expense"),
    ("400", "Advertising", "expense"),
    ("404", "Bank Fees", "expense"),
    ("408", "Cleaning", "expense"),
    ("412", "Consulting & Accounting", "expense"),
    ("416", "Depreciation", "expense"),
    ("420", "Entertainment", "expense"),
    ("425", "Freight & Courier", "expense"),
    (GENERAL_EXPENSES, "General Expenses", "expense"),
    ("433", "Insurance", "expense"),
    ("437", "Interest Expense", "expense"),
    ("441", "Legal expenses", "expense"),
    ("445", "Light, Power, Heating", "expense"),
    ("449", "Motor Vehicle Expenses", "expense"),
    ("453", "Office Expenses", "expense"),
    ("461", "Printing & Stationery", "expense"),
    ("469", "Rent", "expense"),
    ("473", "Repairs and Maintenance", "expense"),
    ("477", "Wages and Salaries", "expense"),
    ("478", "Superannuation", "expense"),
    ("485", "Subscriptions", "expense"),
    ("489", "Telephone & Internet", "expense"),
    ("493", "Travel - National", "expense"),
    ("494", "Travel - International", "expense"),
    (RECEIVABLES, "Accounts Receivable", "asset"),
    ("620", "Prepayments", "asset"),
    (EQUIPMENT, "Office Equipment", "asset"),
    ("720", "Computer Equipment", "asset"),
    (PAYABLES, "Accounts Payable", "liability"),
    ("801", "Unpaid Expense Claims", "liability"),
    (GST, "GST", "liability"),
    ("825", "PAYG Withholdings Payable", "liability"),
    ("826", "Superannuation Payable", "liability"),
    ("830", "Income Tax Payable", "liability"),
    ("850", "Suspense", "liability"),
    (DRAWINGS, "Owner A Drawings", "equity"),
    (FUNDS_INTRODUCED, "Owner A Funds Introduced", "equity"),
    (LOAN, "Loan", "liability"),
    ("960", "Retained Earnings", "equity"),
    ("970", "Owner A Share Capital", "equity"),
]

INCOME_ACCOUNTS = tuple(code for code, _, kind in CHART if kind == "income")
PROFIT_AND_LOSS = tuple(code for code, _, kind in CHART if kind in ("income", "expense"))
CONTROL_ACCOUNTS = (BANK, GST)  # never the "category" of a transaction
OWNER_ACCOUNTS = (DRAWINGS, FUNDS_INTRODUCED)  # owner money: the transaction is Personal

# Old built-in chart -> this chart. GST receivable and GST payable merge into one GST account.
LEGACY = {
    "1000": BANK,
    "1100": RECEIVABLES,
    "1200": GST,
    "1500": EQUIPMENT,
    "2000": PAYABLES,
    "2100": GST,
    "2200": LOAN,
    "3000": DRAWINGS,
    "4000": SALES,
    "4900": OTHER_REVENUE,
    "5000": GENERAL_EXPENSES,
    "5100": "445",
    "5200": "493",
    "5300": "433",
}


def current(code):
    """A code in this chart, also for databases not yet migrated (read-only views)."""
    return LEGACY.get(code, code)


def needs_migration(db):
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ledger_accounts'"
    ).fetchone()
    return bool(exists) and bool(db.execute(
        f"SELECT 1 FROM ledger_accounts WHERE code IN ({','.join('?' * len(LEGACY))})",
        tuple(LEGACY),
    ).fetchone())


def _renumber(journal_json):
    journal = json.loads(journal_json)
    lines = journal.get("lines") if isinstance(journal, dict) else None
    if not isinstance(lines, list):
        return journal_json
    changed = False
    for line in lines:
        if isinstance(line, dict) and line.get("account") in LEGACY:
            line["account"] = LEGACY[line["account"]]
            changed = True
    return json.dumps(journal, sort_keys=True) if changed else journal_json


def migrate(db):
    """Move a database from the old built-in chart to this one. Caller holds the transaction.

    Only codes change: every journal line keeps its amounts, so each journal stays balanced
    and gst_items (the BAS source) are untouched. Audit history is left as written.
    """
    if not needs_migration(db):
        return None
    import bas_applicability
    import product_store
    import supplier_links

    # Reviews and links are bound to hashes of the ledger rows. A renumber changes no
    # substance, so whatever was current before stays current after; stale stays stale.
    current_links = [(r["transaction_id"], r["journal_id"], r["source_nickname"])
                     for r in supplier_links.valid_links(db)]
    old_ledger = bas_applicability.ledger_digest(db)
    old_state = product_store.state_digest(db)
    old = [list(r) for r in db.execute("SELECT code,name,kind FROM ledger_accounts ORDER BY code")]
    db.executemany("INSERT OR IGNORE INTO ledger_accounts VALUES (?,?,?)", CHART)
    lines = 0
    for legacy, new in LEGACY.items():
        lines += db.execute(
            "UPDATE journal_lines SET account_code=? WHERE account_code=?", (new, legacy)
        ).rowcount
    proposals = 0
    for pid, journal_json in db.execute("SELECT id,journal_json FROM proposals").fetchall():
        renumbered = _renumber(journal_json)
        if renumbered != journal_json:
            db.execute("UPDATE proposals SET journal_json=? WHERE id=?", (renumbered, pid))
            proposals += 1
    for tid, jid, nickname in current_links:
        db.execute("UPDATE supplier_bank_links SET snapshot=? WHERE transaction_id=? AND journal_id=?",
                   (supplier_links.fingerprint(db, tid, jid, nickname), tid, jid))
    reviews = db.execute("UPDATE bas_task_reviews SET ledger_digest=? WHERE ledger_digest=?",
                         (bas_applicability.ledger_digest(db), old_ledger)).rowcount
    steps = db.execute("UPDATE workflow_events SET state_digest=? WHERE state_digest=?",
                       (product_store.state_digest(db), old_state)).rowcount
    db.execute(
        f"DELETE FROM ledger_accounts WHERE code IN ({','.join('?' * len(LEGACY))})", tuple(LEGACY)
    )
    result = {"mapping": LEGACY, "journal_lines": lines, "proposals": proposals,
              "supplier_links": len(current_links), "task_reviews": reviews, "workflow_steps": steps}
    db.execute(
        "INSERT INTO audit_events(action,object_type,object_id,before_json,after_json,reason) "
        "VALUES (?,?,?,?,?,?)",
        ("migrate", "ledger_accounts", "xero-au-chart", json.dumps(old), json.dumps(result),
         "Renumbered to the Xero-style Australian chart of accounts; amounts unchanged"),
    )
    return result
