"""Read NAB text transaction listings using their printed column headings."""
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

HEADER = ['Date', 'Details', 'Debits', 'Credits', 'Balance']
MONEY = re.compile(r'^\$[\d,]+\.\d{2}$')


def amount(text):
    return Decimal(text.replace('$', '').replace(',', ''))


def read_listing(pdf):
    """Return header/rows, or None for PDFs outside this supported layout.

    Require summary totals and every printed running balance to reconcile.
    Amount direction comes from columns, never from description or balance.
    """
    first_text = pdf.pages[0].extract_text() or ''
    if 'Transaction Listing' not in first_text or 'Date Details Debits Credits Balance' not in first_text:
        return None
    summary = {}
    for label in ('Start Balance', 'Total Credits', 'Total Debits', 'End Balance'):
        match = re.search(re.escape(label) + r'\s+(\$[\d,]+\.\d{2})(?:\s+(CR|DR))?', first_text)
        if not match or ('Balance' in label and match[2] is None):
            raise ValueError(f'NAB listing missing summary: {label}')
        summary[label] = amount(match[1]) * (-1 if match[2] == 'DR' else 1)
    rows = []
    for page_number, page in enumerate(pdf.pages, 1):
        lines = defaultdict(list)
        for word in page.extract_words():
            lines[round(word['top'], 1)].append(word)
        anchors = None
        current = None
        for _, words in sorted(lines.items()):
            words.sort(key=lambda word: word['x0'])
            text = ' '.join(word['text'] for word in words)
            if text == ' '.join(HEADER):
                anchors = [word['x0'] for word in words]
                continue
            if anchors is None:
                continue
            if text == 'Important':
                break
            match = re.match(r'^(\d{2} [A-Za-z]{3} \d{2})\s', text)
            if match:
                datetime.strptime(match[1], '%d %b %y')
                amounts = [word for word in words if MONEY.fullmatch(word['text'])]
                debits = [word for word in amounts if anchors[2] <= word['x1'] < anchors[3]]
                credits = [word for word in amounts if anchors[3] <= word['x1'] < anchors[4]]
                balances = [word for word in amounts if word['x1'] >= anchors[4]]
                if len(amounts) != 2 or len(debits) + len(credits) != 1 or len(balances) != 1 or words[-1]['text'] not in ('CR', 'DR'):
                    raise ValueError(f'Ambiguous NAB amounts on page {page_number}: {text}')
                description = ' '.join(word['text'] for word in words if anchors[1] - 1 <= word['x0'] < anchors[2] and not MONEY.fullmatch(word['text']))
                balance = amount(balances[0]['text']) * (-1 if words[-1]['text'] == 'DR' else 1)
                current = [match[1], description, debits[0]['text'] if debits else '', credits[0]['text'] if credits else '', balance]
                rows.append(current)
            elif current:
                if words[0]['x0'] < anchors[1] - 1 or any(MONEY.fullmatch(word['text']) for word in words):
                    raise ValueError(f'Unrecognised NAB transaction line on page {page_number}: {text}')
                continuation = ' '.join(word['text'] for word in words if anchors[1] - 1 <= word['x0'] < anchors[2] and not MONEY.fullmatch(word['text']))
                if continuation:
                    current[1] += ' ' + continuation
        if anchors is None:
            raise ValueError(f'NAB listing page {page_number} missing transaction headings')
    balance = summary['Start Balance']
    debit = credit = Decimal(0)
    for index, row in enumerate(rows, 1):
        d = amount(row[2]) if row[2] else Decimal(0)
        c = amount(row[3]) if row[3] else Decimal(0)
        debit += d
        credit += c
        balance += c - d
        if balance != row[4]:
            raise ValueError(f'NAB running balance mismatch at transaction {index}')
    if not rows or debit != summary['Total Debits'] or credit != summary['Total Credits'] or balance != summary['End Balance']:
        raise ValueError('NAB extracted transactions do not reconcile with listing summary')
    return HEADER, rows
