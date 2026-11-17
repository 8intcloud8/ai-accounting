"""What the BAS panel shows, and a watcher that refreshes it as soon as the books change.

Everything here reads the database read-only.
"""

import threading
from contextlib import closing
from pathlib import Path

import bas_dashboard
import next_step
import product_store


def transaction_counts(db_path, start, end):
    """Bank transactions in the period by where they stand: classified, proposed, uncategorised."""
    with closing(bas_dashboard.read_only(db_path)) as db:
        total, classified, proposed = db.execute(
            "SELECT count(*),"
            " sum(EXISTS(SELECT 1 FROM journals j WHERE j.transaction_id=t.id)),"
            " sum(NOT EXISTS(SELECT 1 FROM journals j WHERE j.transaction_id=t.id) AND"
            "     EXISTS(SELECT 1 FROM proposals p WHERE p.transaction_id=t.id AND p.status='proposed'))"
            " FROM transactions t WHERE t.date BETWEEN ? AND ?", (start, end)).fetchone()
    total, classified, proposed = total or 0, classified or 0, proposed or 0
    return {"total": total, "classified": classified, "proposed": proposed,
            "uncategorised": total - classified - proposed}


def next_action(db_path, start, end):
    """The one next piece of work: the question to show and the request that starts it."""
    first = next_step.first_problem(db_path, start, end)
    period = f"{start} to {end}"
    if first is None:
        return {"question": next_step.DONE, "detail": "Every step is done.", "who": "worker",
                "request": bas_dashboard.PREPARE.format(period=period)}
    return {"question": next_step.question(first), "detail": next_step.clean(bas_dashboard.plain(first["text"])),
            "who": first["who"], "request": bas_dashboard.REQUESTS[first["code"]].format(period=period)}


def status(db_path, start, end):
    data = bas_dashboard.snapshot(db_path, start, end)
    data["next"] = next_action(db_path, start, end)
    data["transactions"] = transaction_counts(db_path, start, end)
    return data


class Watcher:
    """Calls `changed` when the database or its write-ahead log changes on disk."""

    def __init__(self, db_path, changed, interval=0.5):
        self.files = [Path(db_path), Path(f"{db_path}-wal")]
        self.changed, self.interval = changed, interval
        self.stopped = threading.Event()
        self.last = self.stamp()

    def stamp(self):
        stamps = []
        for f in self.files:
            try:
                info = f.stat()
                stamps.append((info.st_mtime_ns, info.st_size))
            except OSError:
                stamps.append(None)
        return tuple(stamps)

    def run(self):
        while not self.stopped.wait(self.interval):
            now = self.stamp()
            if now != self.last:
                self.last = now
                self.changed()

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def stop(self):
        self.stopped.set()
