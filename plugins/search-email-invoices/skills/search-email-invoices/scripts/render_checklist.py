"""Render the invoice checklist without changing its approved layout."""
import argparse
import html
import json
import re
import secrets
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlsplit

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def render(result, accounts, destination=""):
    esc = lambda value: html.escape(str(value), quote=True)
    category = result["category"]
    if category not in ("business", "personal", "bills"):
        raise ValueError("Invalid category")
    start, end = (date.fromisoformat(result[k]) for k in ("dateFrom", "dateTo"))
    rows = []
    for bill in result["bills"]:
        url = bill.get("gmailLink", "")
        parsed = urlsplit(url)
        if (len(accounts) == 1 and parsed.netloc == "mail.google.com" and parsed.fragment
                and EMAIL.fullmatch(accounts[0])):
            # Open the searched mailbox, not whichever Google account is signed in first.
            url = f"https://mail.google.com/mail/?authuser={quote(accounts[0])}#{parsed.fragment}"
        link = (f'<a href="{esc(url)}" target="_blank" rel="noopener">Open in Gmail</a>'
                if parsed.scheme == "https" and parsed.netloc == "mail.google.com" else "")
        documents = "<br>".join(esc(x) for x in bill["attachments"]) or "Inline receipt"
        label = esc(f'Select {bill["vendor"]} {bill["date"]}')
        rows.append(f'<tr><td><input class="bill" type="checkbox" checked value="{esc(bill["threadId"])}" data-message="{esc(bill["messageId"])}" aria-label="{label}"></td>'
                    f'<td>{esc(bill["date"])}</td><td><strong>{esc(bill["vendor"])}</strong><br><small>{esc(bill["sender"]["email"])}</small></td>'
                    f'<td>{esc(bill["subject"])}</td><td>{documents}</td><td>{link}</td></tr>')
    attached = sum(bool(b["attachments"]) for b in result["bills"])
    heading = {"business": "Business invoices", "personal": "Personal invoices", "bills": "Bills"}[category]
    period = (f'{start.day} {start:%B}–{end.day} {end:%B %Y}' if start.year == end.year
              else f'{start.day} {start:%B %Y}–{end.day} {end:%B %Y}')
    config = {"category": category, "from": start.isoformat(), "to": end.isoformat(),
              "pickerToken": secrets.token_urlsafe(32), "pickerHome": str(Path.home()),
              "folder": f'{category.title()}/{start.isoformat()}_{end.isoformat()}'}
    values = {"TITLE": esc(f"{heading} — {period}"), "HEADING": heading, "PERIOD": esc(period),
              "ACCOUNTS": esc(" · ".join(accounts)),
              "TOTALS": f'{len(rows)} candidates · {attached} with attachments · {len(rows)-attached} inline',
              "ROWS": "".join(rows) or '<tr><td colspan="6">No invoices found.</td></tr>',
              "DESTINATION": esc(destination),
              "CONFIG": json.dumps(config).replace("<", "\\u003c")}
    template = (Path(__file__).resolve().parents[1] / "assets/checklist.html").read_text()
    # One substitution pass: email text must never become a template directive.
    output = re.sub(r"@@([A-Z]+)@@", lambda match: values[match[1]], template)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON containing result and accounts")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    output = render(data["result"], data["accounts"], data.get("destination", ""))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output)
