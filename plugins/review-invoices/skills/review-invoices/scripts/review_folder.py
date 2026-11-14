"""Serve a reviewed invoice CSV and quarantine only explicitly confirmed rows."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import threading
from datetime import datetime, timezone

import local_server
from local_server import LocalHandler


# Must match the outcome table and document_kind list in SKILL.md, and the
# category filter and status labels in assets/review.html.
OUTCOMES = frozenset({
    "keep_invoice", "keep_receipt", "keep_credit_note", "keep_sale_or_rcti",
    "keep_supporting", "exact_duplicate", "possible_duplicate", "non_invoice",
    "unreadable_needs_review", "control_file",
})
DOCUMENT_KINDS = frozenset({
    "invoice", "receipt", "credit_note", "sale", "supporting", "control",
})

SANDBOX_BLOCKED = local_server.sandbox_blocked(
    "the local review page",
    "Quarantine and restore need this page; there is no chat-only equivalent. "
    "Report this blocker instead of describing the review as opened or applied.",
)


def bind_loopback(handler, port):
    return local_server.bind_loopback(handler, port, SANDBOX_BLOCKED)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_path(root, relative):
    """Refuse symlinks in every component, traversal and hidden/control folders."""
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(
        part in ("..", ".") or part.startswith(".")
        or part in ("output", "_quarantine") for part in path.parts
    ):
        raise ValueError("Choose a reviewed document inside the source folder")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlink documents are not supported")
    if not current.resolve().is_relative_to(root):
        raise ValueError("Document escapes source folder")
    return current


def secure_directory(root, relative):
    current = root
    for part in Path(relative).parts:
        if part in ("..", ".") or "/" in part:
            raise ValueError("Invalid quarantine folder")
        current = current / part
        if current.is_symlink():
            raise ValueError("Quarantine folders must not be symlinks")
        current.mkdir(exist_ok=True)
        if not current.is_dir():
            raise ValueError("Quarantine destination is not a folder")
    return current


def write_log(path, value):
    temp = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as handle:
            os.chmod(temp, 0o600)
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Review:
    def __init__(self, source, report):
        self.root = source.resolve(strict=True)
        # Managed evidence is report-only, including its subdirectories.
        self.read_only = any(
            (p.parent / "db/accounting.db").exists() and p.name == "documents"
            for p in [self.root, *self.root.parents]
        )
        if source.is_symlink() or not self.root.is_dir():
            raise ValueError("Source must be a real directory")
        self.report = report.resolve(strict=True)
        if report.is_symlink() or self.report.suffix.lower() != ".csv" or not self.report.is_file():
            raise ValueError("Choose a regular review CSV")
        self.report_hash = sha256(self.report)
        with self.report.open(newline="", encoding="utf-8-sig") as handle:
            self.rows = list(csv.DictReader(handle))
        self.by_id = {}
        for row in self.rows:
            key = row["row_id"]
            if not key or key in self.by_id:
                raise ValueError("Review row IDs must be unique")
            path = checked_path(self.root, row["relative_path"])
            if len(row["sha256"]) != 64:
                raise ValueError("Review row is missing its file hash")
            # Reject unknown spellings rather than degrade. `protected` below
            # keys off the exact outcome, so a drifted "control_file" would
            # silently make a prior review export or recovery log
            # quarantinable, and a drifted kind drops the row out of the
            # review page's category filter.
            if row["outcome"] not in OUTCOMES:
                raise ValueError(
                    f"Row {key} has unknown outcome {row['outcome']!r}; "
                    f"use one of: {', '.join(sorted(OUTCOMES))}"
                )
            if row["document_kind"] not in DOCUMENT_KINDS and not (
                row["document_kind"] == "" and row["outcome"] == "unreadable_needs_review"
            ):
                raise ValueError(
                    f"Row {key} has unknown document_kind {row['document_kind']!r}; "
                    f"use one of: {', '.join(sorted(DOCUMENT_KINDS))} "
                    "(may be blank only for unreadable_needs_review)"
                )
            row["protected"] = (
                row["outcome"] in ("control_file", "unreadable_needs_review")
                or path.name == "manifest.csv" or path == self.report
                or path.suffix.lower() in (".db", ".sqlite", ".sqlite3")
                or "db" in Path(row["relative_path"]).parts
                or any(p.name == "documents" and (p.parent / "db/accounting.db").exists()
                       for p in path.parents)
            )
            self.by_id[key] = row
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.operations = {}
        self.moved = {}

    def validate_source(self, row):
        path = checked_path(self.root, row["relative_path"])
        if not path.exists() or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("Document is missing or no longer a regular file")
        if path.stat().st_size != int(row["size_bytes"]) or sha256(path) != row["sha256"]:
            raise ValueError("Document changed since review; review it again")
        return path

    def move(self, request):
        with self.lock:
            if self.read_only:
                raise ValueError("Managed accounting evidence is read-only")
            if request.get("report_sha256") != self.report_hash or sha256(self.report) != self.report_hash:
                raise ValueError("The review changed; reload and review again")
            ids = request.get("row_ids")
            reason = request.get("reason", "")
            if not isinstance(ids, list) or not ids or len(ids) > len(self.rows):
                raise ValueError("Select at least one reviewed document")
            if any(not isinstance(key, str) for key in ids) or len(set(ids)) != len(ids):
                raise ValueError("Invalid selection")
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
                raise ValueError("Provide a reason for this selection")
            plans = []
            run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
            for key in ids:
                if key not in self.by_id or key in self.moved:
                    raise ValueError("Unknown or already moved review row")
                row = self.by_id[key]
                if row["protected"]:
                    raise ValueError("Managed evidence, databases, unreadable files and control exports must be preserved")
                if row["outcome"] == "unreadable_needs_review":
                    raise ValueError("Resolve unreadable documents before cleanup")
                path = self.validate_source(row)
                outcome = row["outcome"]
                folder = {"exact_duplicate": "duplicates", "keep_supporting": "supporting",
                          "non_invoice": "non-invoices"}.get(outcome, "selected")
                if outcome == "exact_duplicate":
                    keeper = row.get("keeper_relative_path", "")
                    retained = checked_path(self.root, keeper)
                    if any(self.by_id[k]["relative_path"] == keeper for k in ids if k in self.by_id):
                        raise ValueError("The duplicate keeper is also selected")
                    if not retained.is_file() or sha256(retained) != row["sha256"] or retained.read_bytes() != path.read_bytes():
                        raise ValueError("Duplicate keeper changed or does not match")
                relative = Path("_quarantine") / run / folder / row["relative_path"]
                dest_dir = secure_directory(self.root, relative.parent)
                target = dest_dir / path.name
                if target.exists() or target.is_symlink():
                    raise ValueError("Destination exists; nothing overwritten")
                plans.append({"row_id": key, "original": str(path), "destination": str(target),
                              "sha256": row["sha256"], "reason": reason.strip(),
                              "review_reason": row["reason"], "status": "pending"})
            log_path = self.root / "_quarantine" / run / "recovery.json"
            record = {"run_id": run, "source_root": str(self.root), "report": str(self.report),
                      "report_sha256": self.report_hash, "approval": "Explicit selection and confirmation in local review page",
                      "created_at": datetime.now(timezone.utc).isoformat(), "files": plans}
            write_log(log_path, record)
            for item in plans:
                try:
                    source = self.validate_source(self.by_id[item["row_id"]])
                    target = Path(item["destination"])
                    # Exclusive link prevents overwriting even if a collision appears
                    # after preflight. Both paths are on the same source filesystem.
                    os.link(source, target, follow_symlinks=False)
                    if sha256(target) != item["sha256"]:
                        target.unlink()
                        raise ValueError("Destination verification failed; original retained")
                    source.unlink()
                    item["status"] = "moved"
                    item["moved_at"] = datetime.now(timezone.utc).isoformat()
                    self.moved[item["row_id"]] = item
                except (OSError, ValueError) as error:
                    item["status"] = "failed"
                    item["error"] = str(error)
                write_log(log_path, record)
            self.operations[run] = log_path
            return {"run_id": run, "recovery_log": str(log_path), "files": plans,
                    "moved_count": sum(p["status"] == "moved" for p in plans)}

    def restore(self, run):
        with self.lock:
            if run not in self.operations:
                raise ValueError("Unknown recovery run")
            log_path = self.operations[run]
            if log_path.is_symlink():
                raise ValueError("Recovery log changed")
            record = json.loads(log_path.read_text())
            for item in record["files"]:
                if item["status"] != "moved":
                    continue
                row_id = item["row_id"]
                original = checked_path(self.root, self.by_id[row_id]["relative_path"])
                expected = self.moved.get(row_id)
                if not expected or item["destination"] != expected["destination"] or item["sha256"] != self.by_id[row_id]["sha256"]:
                    raise ValueError("Recovery record does not match this review")
                destination = Path(item["destination"])
                if not destination.resolve().is_relative_to(self.root / "_quarantine" / run):
                    raise ValueError("Invalid recovery destination")
                if any(p.is_symlink() for p in [destination, *destination.parents] if p.is_relative_to(self.root)):
                    raise ValueError("Recovery destination contains a symlink")
                if original.exists() or original.is_symlink():
                    item["restore_error"] = "Original path exists; nothing overwritten"
                elif not destination.is_file() or sha256(destination) != item["sha256"]:
                    item["restore_error"] = "Quarantined file changed; review manually"
                else:
                    os.link(destination, original, follow_symlinks=False)
                    destination.unlink()
                    item["status"] = "restored"
                    item["restored_at"] = datetime.now(timezone.utc).isoformat()
                    self.moved.pop(row_id, None)
                write_log(log_path, record)
            return {"files": record["files"], "recovery_log": str(log_path)}


def create_server(review, port=0):
    assets = Path(__file__).parent.parent / "assets"
    template = (assets / "review.html").read_text().replace(
        "CHECKLIST_STYLE", (assets / "checklist.css").read_text()
    )

    class Handler(LocalHandler):
        def send(self, body, mime="application/json", status=200):
            self.reply(status, body, mime)

        def authenticated(self):
            return self.local_host() and self.token_matches(self.query("token"), review.token)

        def do_GET(self):
            if not self.authenticated():
                self.send_error(403)
                return
            route = self.route()
            try:
                if route == "/":
                    data = json.dumps({"rows": review.rows, "token": review.token,
                                       "report_sha256": review.report_hash, "source": str(review.root),
                                       "moved": list(review.moved), "read_only": review.read_only})
                    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
                    self.send(template.replace("REVIEW_DATA", data).encode(), "text/html; charset=utf-8")
                elif route == "/export":
                    self.send(review.report.read_bytes(), "text/csv; charset=utf-8")
                elif route.startswith("/document/"):
                    key = route.rsplit("/", 1)[-1]
                    if key not in review.by_id:
                        raise ValueError("Unknown document")
                    if key in review.moved:
                        raise ValueError("Document is in quarantine; use the recovery log")
                    path = checked_path(review.root, review.by_id[key]["relative_path"])
                    self.send(path.read_bytes(), "application/pdf" if path.suffix.lower() == ".pdf" else "text/plain; charset=utf-8")
                else:
                    self.send_error(404)
            except (ValueError, OSError) as error:
                self.send(str(error).encode(), "text/plain; charset=utf-8", 400)

        def do_POST(self):
            if (not self.authenticated() or not self.same_origin()
                    or not self.token_matches(self.headers.get("X-Review-Token"), review.token)
                    or self.headers.get("Content-Type") != "application/json"):
                self.send_error(403)
                return
            try:
                request = self.read_json(16384)
                route = self.route()
                if route == "/quarantine":
                    result = review.move(request)
                elif route == "/restore":
                    result = review.restore(request.get("run_id"))
                else:
                    raise ValueError("Unknown operation")
                self.send(json.dumps(result).encode())
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.send(json.dumps({"error": str(error)}).encode(), status=400)

    server = bind_loopback(Handler, port)
    server.review_url = local_server.url(server, review.token)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    review = Review(args.source, args.csv)
    server = create_server(review, args.port)
    print(json.dumps({"review_url": server.review_url}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
