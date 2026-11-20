"""Bank rules, as in Xero: code matching bank lines the same way every time.

A rule is made from a journal the user already confirmed ("make this a rule"): it keeps
that journal's accounts, business/private split, GST label and ATO source, plus the
text to match. Applying rules turns each matching, still-open bank line into a
proposal scaled to its amount, which the user OKs like any other proposal. Rules never
post on their own, and ending a rule keeps it in the list for the record.
"""

import json
import re
from contextlib import closing
from datetime import date

import chart
import proposal_store

SCHEMA = """
CREATE TABLE IF NOT EXISTS bank_rules (
 id INTEGER PRIMARY KEY, match TEXT NOT NULL, template_json TEXT NOT NULL,
 from_journal INTEGER NOT NULL REFERENCES journals(id), note TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, ended_at TEXT, ended_reason TEXT);
"""


def normal(text):
    return " ".join(re.sub(r"[^a-z0-9&.'-]+", " ", (text or "").lower()).split())


def matches(match, description):
    """Whole-word match, so 'aldi' never matches 'baldivis'."""
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(normal(match)) + r"(?![a-z0-9])", normal(description)))


def stored_source(db, journal_id):
    """The journal's saved GST source, as the request form proposals need."""
    row = db.execute("SELECT verified,url,section,accessed,note FROM gst_sources WHERE journal_id=?",
                     (journal_id,)).fetchone()
    if not row:
        return None
    verified, url, section, accessed, note = row
    if not verified:
        return {"verified": False, "note": note}
    if url.startswith("ato-library:"):
        sha, _, page = url.removeprefix("ato-library:").partition("#page=")
        return {"library": {"sha256": sha, "page": int(page), "quote": (note or "").strip('"')}}
    return {k: v for k, v in (("url", url), ("section", section), ("accessed", accessed), ("note", note)) if v}


def template(db, journal_id, source=None):
    """The coding of a confirmed journal, ready to scale onto another bank line."""
    if db.execute("SELECT 1 FROM journals WHERE reverses_id=? OR (id=? AND reverses_id IS NOT NULL)",
                  (journal_id, journal_id)).fetchone():
        raise ValueError(f"Journal {journal_id} is reversed or a reversal; make the rule from the current one")
    head = db.execute("SELECT description,transaction_id FROM journals WHERE id=?", (journal_id,)).fetchone()
    if not head:
        raise ValueError(f"Unknown journal {journal_id}")
    if head[1] is None:
        raise ValueError("A bank rule needs a journal for a bank transaction")
    lines = [{"account": a, "debit_cents": d, "credit_cents": c} for a, d, c in db.execute(
        "SELECT account_code,debit_cents,credit_cents FROM journal_lines WHERE journal_id=? ORDER BY line_no",
        (journal_id,))]
    gst = db.execute("SELECT label,gross_cents,gst_cents,status FROM gst_items WHERE journal_id=?",
                     (journal_id,)).fetchone()
    if not gst or gst[3] != "reviewed":
        raise ValueError("A bank rule needs a journal whose GST is reviewed")
    source = source or stored_source(db, journal_id)
    if not source:
        raise ValueError("That journal has no saved ATO source; pass one as \"source\"")
    return {"lines": lines, "gst": {"label": gst[0], "gross_cents": gst[1], "gst_cents": gst[2],
                                    "source": source}}


def bank_cents(lines):
    """Money out is positive, money in negative."""
    return sum(l["credit_cents"] - l["debit_cents"] for l in lines if chart.current(l["account"]) == chart.BANK)


def scaled(rule_template, amount):
    """The template's lines and GST for a bank line of `amount` cents (out positive).
    Rounding goes to the largest non-bank, non-GST line so the journal still balances."""
    old = bank_cents(rule_template["lines"])
    if not old or (old > 0) != (amount > 0):
        return None  # money the other way: the rule does not fit
    ratio = amount / old
    lines = [{"account": l["account"], "debit_cents": round(l["debit_cents"] * ratio),
              "credit_cents": round(l["credit_cents"] * ratio)} for l in rule_template["lines"]]
    for l in lines:
        if chart.current(l["account"]) == chart.BANK:  # the bank side is exact
            want = l["credit_cents"] - l["debit_cents"]
            if want:
                l["credit_cents"], l["debit_cents"] = (amount, 0) if amount > 0 else (0, -amount)
    gap = sum(l["debit_cents"] - l["credit_cents"] for l in lines)
    if gap:
        free = [l for l in lines if chart.current(l["account"]) not in (chart.BANK, chart.GST)]
        target = max(free, key=lambda l: l["debit_cents"] + l["credit_cents"])
        if target["debit_cents"]:
            target["debit_cents"] -= gap
        else:
            target["credit_cents"] += gap
    lines = [l for l in lines if l["debit_cents"] or l["credit_cents"]]
    if any(l["debit_cents"] < 0 or l["credit_cents"] < 0 for l in lines):
        return None
    gst = dict(rule_template["gst"])
    gst["gross_cents"] = round(gst["gross_cents"] * ratio)
    gst_net = sum(abs(l["debit_cents"] - l["credit_cents"]) for l in lines if chart.current(l["account"]) == chart.GST)
    gst["gst_cents"] = gst_net if rule_template["gst"]["gst_cents"] is not None else None
    return lines, gst


def save_rule(path, payload, connect):
    """Make a rule from a confirmed journal. Payload: journal_id, match, optional note/source."""
    journal_id, match = payload.get("journal_id"), payload.get("match")
    if not isinstance(journal_id, int) or not isinstance(match, str) or len(normal(match)) < 3:
        raise ValueError("A rule needs journal_id and match text of at least 3 letters")
    with closing(connect(path)) as db, db:
        db.executescript(SCHEMA)
        built = template(db, journal_id, payload.get("source"))
        description = db.execute("SELECT t.description FROM journals j JOIN transactions t ON t.id=j.transaction_id "
                                 "WHERE j.id=?", (journal_id,)).fetchone()[0]
        if not matches(match, description):
            raise ValueError(f"\"{match}\" does not appear in that bank line ({description})")
        clash = db.execute("SELECT id FROM bank_rules WHERE ended_at IS NULL AND match=?", (normal(match),)).fetchone()
        if clash:
            raise ValueError(f"Rule {clash[0]} already matches \"{match}\"; end it first")
        cur = db.execute("INSERT INTO bank_rules(match,template_json,from_journal,note) VALUES(?,?,?,?)",
                         (normal(match), json.dumps(built, sort_keys=True), journal_id, payload.get("note")))
    return {"rule": cur.lastrowid, "match": normal(match)}


def end_rule(path, payload, connect):
    rule = payload.get("id")
    with closing(connect(path)) as db, db:
        db.executescript(SCHEMA)
        done = db.execute("UPDATE bank_rules SET ended_at=?,ended_reason=? WHERE id=? AND ended_at IS NULL",
                          (date.today().isoformat(), payload.get("reason"), rule)).rowcount
    if not done:
        raise ValueError(f"No active rule {rule}")
    return {"ended": rule}


def rows(db):
    """Every rule, newest first, in plain words: what it matches and how it codes.
    Needs the table to exist; works on a read-only connection."""
    names = dict(db.execute("SELECT code,name FROM ledger_accounts"))
    import xero_tax

    result = []
    for rid, match, raw, journal, note, created, ended, why in db.execute(
            "SELECT id,match,template_json,from_journal,note,created_at,ended_at,ended_reason "
            "FROM bank_rules ORDER BY id DESC"):
        t = json.loads(raw)
        accounts = [l["account"] for l in t["lines"]]
        coded = [f"{a} {names.get(a, '')}".strip() for a in accounts
                 if chart.current(a) not in proposal_store.CONTROL_ACCOUNTS]
        g = t["gst"]
        result.append({"id": rid, "match": match, "accounts": coded,
                       "tax_rate": xero_tax.rate(g["label"], g["gst_cents"], "reviewed", accounts)[0],
                       "from_journal": journal, "note": note, "created": created[:10],
                       "status": "Ended" if ended else "Active", "ended": ended, "ended_reason": why})
    return result


def listing(path, connect):
    with closing(connect(path)) as db:
        db.executescript(SCHEMA)
        return {"rules": rows(db)}


def apply(path, start, end, connect):
    """Propose a journal for every open bank line in the period that an active rule matches."""
    with closing(connect(path)) as db:
        db.executescript(SCHEMA)
        rules = [(rid, match, json.loads(raw)) for rid, match, raw in db.execute(
            "SELECT id,match,template_json FROM bank_rules WHERE ended_at IS NULL")]
        rules.sort(key=lambda r: -len(r[1]))  # most specific match wins
        open_lines = db.execute(
            "SELECT t.id,t.date,t.description,t.debit_cents,t.credit_cents FROM transactions t "
            "WHERE t.date BETWEEN ? AND ? AND NOT EXISTS(SELECT 1 FROM journals j WHERE j.transaction_id=t.id) "
            "AND NOT EXISTS(SELECT 1 FROM proposals p WHERE p.transaction_id=t.id AND p.status='proposed') "
            "ORDER BY t.date,t.id", (start, end)).fetchall()
    proposals, skipped = [], []
    for tid, day, text, out, into in open_lines:
        rule = next((r for r in rules if matches(r[1], text)), None)
        if not rule:
            continue
        built = scaled(rule[2], out - into)
        if not built:
            skipped.append({"transaction_id": tid, "rule": rule[0], "why": "money moves the other way"})
            continue
        lines, gst = built
        gst.update(status="reviewed", attribution_date=day,
                   evidence=f"Bank rule {rule[0]} (\"{rule[1]}\"), coded like journal from the confirmed rule")
        proposals.append({"journal": {
            "reference": f"rule{rule[0]}-txn{tid}", "date": day, "description": text, "transaction_id": tid,
            "lines": lines, "gst": gst},
            "reason": f"Bank rule {rule[0]}: \"{rule[1]}\" always coded this way"})
    saved = proposal_store.save(path, {"proposals": proposals}, connect)["saved"] if proposals else []
    return {"proposed": len(saved), "proposal_ids": saved, "skipped": skipped}
