"""Suggest Business / Personal / Shared for lines on a personal card or account.

A personal card mostly pays personal things and sometimes pays for the business. Each
line is scored from evidence already in the workspace, strongest first:

0. remembered rule - the user said so in case memory, e.g. topic supplier.aldi.purpose =
               "Personal" (strong; only user_confirmed facts in force on the line's date)
1. invoice   - a saved invoice or receipt for the same amount, near the date, from a
               supplier whose name matches the line (strong: Business)
2. history   - how the same payee was decided before, in any period (strong)
3. business account - the same payee is also paid from a business account (medium)
4. merchant type    - what kind of merchant it is (medium; Shared means mixed use)

Nothing here is saved or posted. The output is for Codex: confident suggestions are
shown to the user in one batch to OK, and only uncertain payees become questions.
"""

import re
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import chart
import memory_store
import proposal_store
import transaction_purpose

INVOICE_DAYS_BEFORE, INVOICE_DAYS_AFTER = 10, 5   # invoice date relative to the card charge
FX_TOLERANCE = 0.03                               # foreign-currency invoices: card amount may differ by 3%
REVIEW_ABOVE_CENTS = 30000                        # personal-looking charges above $300 still get a glance

# Merchant words -> likely purpose. Shared = used both ways; needs a business-use percentage.
MERCHANT_TYPES = {
    "Business": (
        "aws", "amazon web services", "google cloud", "google workspace", "gsuite", "microsoft", "office 365",
        "xero", "myob", "quickbooks", "adobe", "github", "atlassian", "openai", "anthropic", "claude",
        "canva", "figma", "notion", "slack", "zoom", "dropbox", "digitalocean", "heroku", "vercel",
        "cloudflare", "godaddy", "crazy domains", "ventraip", "namecheap", "squarespace", "wix", "shopify",
        "mailchimp", "linkedin", "asic", "ato", "australian taxation", "officeworks", "upwork", "fiverr",
        "stripe", "seek", "abn", "business",
    ),
    "Personal": (
        "woolworths", "coles", "aldi", "iga", "harris farm", "netflix", "spotify", "disney", "stan",
        "binge", "kayo", "foxtel", "youtube premium", "apple music", "uber eats", "menulog", "doordash",
        "deliveroo", "mcdonald", "kfc", "hungry jack", "domino", "subway", "guzman", "grill", "cafe",
        "coffee", "bakery", "restaurant", "sushi", "pizza", "bar", "pub", "liquor",
        "dan murphy", "bws", "chemist", "pharmacy", "priceline", "medicare", "dental", "doctor",
        "kmart", "big w", "target", "myer", "david jones", "uniqlo", "cotton on", "zara", "h&m",
        "rebel", "event cinemas", "hoyts", "gym", "fitness", "anytime fitness", "tab", "sportsbet",
        "lotto", "childcare", "school", "pet", "vet", "bunnings", "ikea",
    ),
    "Shared": (
        "telstra", "optus", "vodafone", "tpg", "aussie broadband", "iinet", "belong", "boost",
        "internet", "mobile", "bp", "shell", "ampol", "caltex", "7-eleven", "7 eleven", "united petrol",
        "metro petroleum", "fuel", "linkt", "e-toll", "etoll", "toll", "parking", "wilson parking",
        "secure parking", "uber", "didi", "ola", "taxi", "agl", "origin energy", "energyaustralia",
        "red energy", "alinta", "electricity", "gas", "nrma", "racv", "rego", "service nsw",
        "vicroads", "car wash", "jb hi-fi", "jb hifi", "harvey norman", "apple.com", "apple store",
    ),
}
# Card repayments and transfers are not purchases at all.
NOT_A_PURCHASE = ("payment thank you", "payment received", "thank you payment", "bpay payment",
                  "transfer from", "transfer to", "direct credit", "autopay", "repayment")
STRENGTH = {"strong": 3, "medium": 2, "weak": 1}
STOP_WORDS = {"pty", "ltd", "limited", "inc", "llc", "the", "and", "com", "www", "au", "sydney",
              "melbourne", "brisbane", "perth", "adelaide", "nsw", "vic", "qld", "card", "purchase"}


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if w not in STOP_WORDS}


def _days(a, b):
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def personal_accounts(db):
    """Imported account ids that belong to a confirmed personal payment source."""
    suffixes = [s for (s,) in db.execute("SELECT suffix FROM payment_sources WHERE owner='personal' AND suffix<>''")]
    return {a for (a,) in db.execute("SELECT DISTINCT account_id FROM transactions")
            if any(a.endswith(s) for s in suffixes)}


def _invoice(db, tx, invoices):
    """Saved invoice/receipt that matches this charge: amount, date window, supplier name."""
    amount, words = tx["debit_cents"], _words(tx["description"])
    for inv in invoices:
        if not inv["total_cents"] or not inv["invoice_date"] or not (words & _words(inv["supplier"])):
            continue
        if not -INVOICE_DAYS_BEFORE <= _days(tx["date"], inv["invoice_date"]) <= INVOICE_DAYS_AFTER:
            continue
        foreign = (inv["currency"] or "AUD").upper() != "AUD"
        close = abs(inv["total_cents"] - amount) <= (amount * FX_TOLERANCE if foreign else 0)
        if close:
            return inv
    return None


def _history(db, personal, purposes):
    """payee -> {purpose: count} from earlier decisions on any account."""
    seen = {}

    def add(text, purpose):
        counts = seen.setdefault(proposal_store.payee(text), {})
        counts[purpose] = counts.get(purpose, 0) + 1

    for tid, item in purposes.items():
        row = db.execute("SELECT description FROM transactions WHERE id=?", (tid,)).fetchone()
        if row:
            add(row[0], item["purpose"])
    for tid, text, account, code in db.execute(
            "SELECT t.id,t.description,t.account_id,l.account_code FROM transactions t "
            "JOIN journals j ON j.transaction_id=t.id AND j.reverses_id IS NULL "
            "AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id) "
            "JOIN journal_lines l ON l.journal_id=j.id"):
        code = chart.current(code)
        if tid in purposes or code in chart.CONTROL_ACCOUNTS or account not in personal:
            continue
        add(text, "Personal" if code in chart.OWNER_ACCOUNTS else "Business")
    return seen


def _normal(text):
    return " ".join(re.sub(r"[^a-z0-9&.'-]+", " ", (text or "").lower()).split())


def _remembered(path, business_id):
    """[(name, history)] for supplier.<name>.purpose facts in the workspace's case memory."""
    try:
        facts = memory_store.read(Path(path).resolve().parent.parent, business_id, history=True)["facts"]
    except (ValueError, OSError, sqlite3.Error):
        return []
    rules = {}
    for fact in facts:
        parts = fact["topic"].split(".")
        if len(parts) == 3 and parts[0] == "supplier" and parts[2] == "purpose":
            name = _normal(parts[1].replace("_", " ").replace("-", " "))
            if name:
                rules.setdefault(name, []).append(fact)
    return list(rules.items())


def _rule(rules, text, on):
    """The user's remembered purpose for this payee on this date, as (purpose, name, fact)."""
    low = _normal(text)
    for name, facts in sorted(rules, key=lambda r: -len(r[0])):  # most specific name first
        if not re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", low):
            continue
        current = None
        for fact in facts:  # effective_from order, later revisions win
            if fact["effective_from"] <= on:
                current = fact
        if not current or current["status"] != "user_confirmed" or (
                current["effective_to"] and on >= current["effective_to"]):
            continue
        value = current["value"]
        value = value.get("purpose") if isinstance(value, dict) else value
        purpose = str(value or "").strip().capitalize()
        if purpose in ("Business", "Personal", "Shared"):
            return purpose, name, current
    return None


def _merchant_type(text):
    """Most specific whole-word match wins ('uber eats' beats 'uber'; 'ato' never matches 'potato')."""
    low = _normal(text)  # 'UBER *EATS' -> 'uber eats'
    best = (0, None, None)
    for purpose in ("Business", "Shared", "Personal"):
        for word in MERCHANT_TYPES[purpose]:
            word = word.strip()
            if len(word) > best[0] and re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", low):
                best = (len(word), purpose, word)
    return best[1], best[2]


def _decide(signals):
    """Strongest agreeing evidence wins; strong signals that disagree mean ask."""
    if not signals:
        return "", "low"
    best = max(STRENGTH[s["strength"]] for s in signals)
    top = {s["purpose"] for s in signals if STRENGTH[s["strength"]] == best}
    if len(top) > 1:
        return "", "low"
    purpose = top.pop()
    against = [s for s in signals if s["purpose"] != purpose and STRENGTH[s["strength"]] >= 2]
    if best == 3 and not against:
        return purpose, "high"
    if best == 3 or (best == 2 and not against):
        return purpose, "medium"
    return purpose, "low"


def _decided_ids(db):
    """Lines already finished: a live journal, a supplier evidence link or a reviewed purpose."""
    done = {t for (t,) in db.execute(
        "SELECT transaction_id FROM journals j WHERE transaction_id IS NOT NULL AND reverses_id IS NULL "
        "AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id)")}
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='supplier_bank_links'").fetchone():
        done |= {t for (t,) in db.execute("SELECT transaction_id FROM supplier_bank_links")}
    return done | set(transaction_purpose.reviewed(db))


def suggest(path, start, end, connect):
    """Suggestions for undecided personal-account lines in the period, grouped by payee."""
    with closing(connect(path)) as db:
        db.row_factory = sqlite3.Row
        personal = personal_accounts(db)
        if not personal:
            return {"personal_accounts": [], "lines": [], "groups": [], "ask": [],
                    "note": "No personal card or account is recorded as a payment source."}
        purposes = transaction_purpose.reviewed(db)
        history = _history(db, personal, purposes)
        business_payees = {proposal_store.payee(t) for (t,) in db.execute(
            "SELECT description FROM transactions WHERE account_id NOT IN (%s)" % ",".join("?" * len(personal)),
            tuple(personal))}
        invoices = [dict(r) for r in db.execute(
            "SELECT id,supplier,invoice_number,invoice_date,currency,total_cents,kind FROM invoices "
            "WHERE kind<>'credit_note'")]
        used_invoices, done = set(), _decided_ids(db)
        profile = db.execute("SELECT business_id,entity_type FROM workspace_profile WHERE id=1").fetchone()
        entity = profile["entity_type"] if profile else "company"
        rules = _remembered(path, profile["business_id"]) if profile else []
        lines = []
        for tx in db.execute(
                "SELECT * FROM transactions WHERE date BETWEEN ? AND ? AND account_id IN (%s) ORDER BY date,id"
                % ",".join("?" * len(personal)), (start, end, *personal)):
            if tx["id"] in done:
                continue
            text, key = tx["description"], proposal_store.payee(tx["description"])
            low = text.lower()
            if any(p in low for p in NOT_A_PURCHASE):
                lines.append(_line(tx, key, "Transfer", "high", [{"signal": "not a purchase", "purpose": "Transfer",
                             "strength": "strong", "detail": "card repayment or transfer"}]))
                continue
            signals = []
            told = _rule(rules, text, tx["date"])
            if told:
                purpose, name, fact = told
                signals.append({"signal": "remembered rule", "purpose": purpose, "strength": "strong",
                                "memory_id": fact["id"],
                                "detail": f"you said '{name}' is {purpose.lower()} (from {fact['effective_from']})"})
            if tx["debit_cents"]:
                inv = _invoice(db, tx, [i for i in invoices if i["id"] not in used_invoices])
                if inv:
                    used_invoices.add(inv["id"])
                    signals.append({"signal": "invoice", "purpose": "Business", "strength": "strong",
                                    "invoice_id": inv["id"],
                                    "detail": f"{inv['kind']} from {inv['supplier']} {inv['invoice_number'] or ''} "
                                              f"dated {inv['invoice_date']} for ${inv['total_cents'] / 100:,.2f}".replace("  ", " ")})
            counts = history.get(key, {})
            if counts:
                purpose = max(counts, key=counts.get)
                unanimous = len(counts) == 1
                signals.append({"signal": "history", "purpose": purpose,
                                "strength": "strong" if unanimous else "weak",
                                "detail": "decided before: " + ", ".join(f"{n} {p}" for p, n in sorted(counts.items()))})
            if key in business_payees:
                signals.append({"signal": "business account", "purpose": "Business", "strength": "medium",
                                "detail": "same payee is also paid from a business account"})
            kind, word = _merchant_type(text)
            if kind:
                signals.append({"signal": "merchant type", "purpose": kind, "strength": "medium",
                                "detail": f"'{word}' usually means {kind.lower()}"
                                          + (" (mixed use: needs a business-use %)" if kind == "Shared" else "")})
            purpose, confidence = _decide(signals)
            if purpose == "Personal" and confidence == "high" and tx["debit_cents"] > REVIEW_ABOVE_CENTS:
                confidence = "medium"  # large personal-looking charges get a look
            lines.append(_line(tx, key, purpose, confidence, signals))
        groups = _groups(lines)
    funding = chart.FUNDS_INTRODUCED if entity == "sole_trader" else chart.LOAN
    return {"personal_accounts": sorted(personal), "lines": lines, "groups": groups,
            "ask": [g for g in groups if g["needs_user"]],
            "business_funding_account": funding,
            "how_to_record": {
                "Business": f"post the expense and GST (tax invoice needed) with the credit to {funding} "
                            f"{'Owner A Funds Introduced' if funding == chart.FUNDS_INTRODUCED else 'Loan (owed to the director)'}",
                "Personal": "review-transaction-purpose with outside_bas=true: no expense, no GST",
                "Shared": "ask the business-use %, then allocate-running-costs; never assume a %",
                "Transfer": "card repayment or transfer: not a purchase, no GST"}}


def _line(tx, key, purpose, confidence, signals):
    return {"transaction_id": tx["id"], "date": tx["date"], "description": tx["description"], "payee": key,
            "amount": (tx["debit_cents"] or -tx["credit_cents"]) / 100,
            "suggested": purpose, "confidence": confidence, "signals": signals}


def _groups(lines):
    """One row per payee so the user answers once per merchant, not once per charge."""
    result = {}
    for line in lines:
        g = result.setdefault(line["payee"], {"payee": line["payee"], "example": line["description"],
                                              "transaction_ids": [], "total": 0.0, "suggestions": {}})
        g["transaction_ids"].append(line["transaction_id"])
        g["total"] = round(g["total"] + line["amount"], 2)
        k = (line["suggested"], line["confidence"])
        g["suggestions"][k] = g["suggestions"].get(k, 0) + 1
    out = []
    for g in result.values():
        kinds = {p for p, _ in g["suggestions"]}
        weakest = min((c for _, c in g["suggestions"]), key=["low", "medium", "high"].index)
        purpose = kinds.pop() if len(kinds) == 1 else ""
        g["suggested"], g["confidence"] = purpose, weakest if purpose else "low"
        g["needs_user"] = not purpose or g["confidence"] == "low" or purpose == "Shared"
        g["suggestions"] = [{"purpose": p, "confidence": c, "count": n} for (p, c), n in g["suggestions"].items()]
        out.append(g)
    return sorted(out, key=lambda g: (not g["needs_user"], -abs(g["total"])))
