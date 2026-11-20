"""Lock date, as in Xero: once a BAS is lodged, nothing on or before the date changes.

Posting or reversing a journal dated on or before the lock date is refused. Moving the
date (or clearing it) is an audited change with a reason, so unlocking is deliberate.
"""

from contextlib import closing
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS lock_date (
 id INTEGER PRIMARY KEY CHECK(id=1), lock_date TEXT, reason TEXT NOT NULL,
 set_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""


def current(db):
    """The lock date (YYYY-MM-DD) or None. Works on a read-only connection."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='lock_date'").fetchone():
        return None
    row = db.execute("SELECT lock_date FROM lock_date WHERE id=1").fetchone()
    return row[0] if row else None


def check(db, day, what="journal"):
    """Refuse a change dated on or before the lock date."""
    locked = current(db)
    if locked and day <= locked:
        raise ValueError(f"The books are locked up to {locked}: this {what} is dated {day}. "
                         "Ask the user whether to move the lock date (set-lock-date) before changing a lodged period")


def set_lock(path, payload, connect, audit):
    """Payload: date (YYYY-MM-DD, or null to unlock) and reason."""
    new, reason = payload.get("date"), payload.get("reason")
    if new is not None:
        new = date.fromisoformat(new).isoformat()
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Changing the lock date needs a reason")
    with closing(connect(path)) as db, db:
        db.executescript(SCHEMA)
        old = current(db)
        db.execute("INSERT INTO lock_date(id,lock_date,reason) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET "
                   "lock_date=excluded.lock_date,reason=excluded.reason,set_at=CURRENT_TIMESTAMP", (new, reason.strip()))
        audit(db, "set_lock_date", "lock_date", 1, {"lock_date": old}, {"lock_date": new}, reason.strip())
    return {"lock_date": new, "previous": old}
