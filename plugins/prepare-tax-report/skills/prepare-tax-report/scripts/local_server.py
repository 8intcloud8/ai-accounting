"""Shared loopback server pieces for the package's local browser pages.

Every page server (review table, invoice folder review, email checklist) binds,
authenticates and answers through this module so there is one place to secure.
"""

import errno
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

LOOPBACK = "127.0.0.1"
SANDBOX_ERRORS = (errno.EPERM, errno.EACCES, errno.EAFNOSUPPORT)
DEFAULT_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


def sandbox_blocked(page: str, fallback: str) -> str:
    """Message for a host that denies loopback, with the Codex remedy."""
    return (
        f"Cannot start {page}: this host blocked the loopback port.\n"
        "Codex sandboxes shell commands and denies all network access by default, "
        f"including {LOOPBACK}.\n"
        "To enable it, add to ~/.codex/config.toml and restart Codex:\n"
        "\n"
        "    [sandbox_workspace_write]\n"
        "    network_access = true\n"
        "\n" + fallback
    )


def bind_loopback(handler, port: int, blocked: str, busy: str | None = None):
    """Bind loopback only. A sandbox denial exits with `blocked` instead of a bare
    EPERM; a taken port exits with `busy` when given, else propagates."""
    try:
        server = ThreadingHTTPServer((LOOPBACK, port), handler)
    except PermissionError as error:
        raise SystemExit(blocked) from error
    except OSError as error:
        if error.errno in SANDBOX_ERRORS:
            raise SystemExit(blocked) from error
        if error.errno == errno.EADDRINUSE and busy:
            raise SystemExit(busy) from error
        raise
    server.daemon_threads = True
    return server


def url(server, token: str | None = None) -> str:
    base = f"http://{LOOPBACK}:{server.server_port}/"
    return f"{base}?token={token}" if token else base


class LocalHandler(BaseHTTPRequestHandler):
    """Request checks and hardened responses shared by every local page."""

    csp = DEFAULT_CSP

    def log_message(self, *_args):
        pass  # Never log URL tokens or financial records.

    def reply(self, status: int, body, mime: str = "application/json", extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", self.csp)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def local_host(self) -> bool:
        """Reject DNS-rebinding: the Host header must be this loopback server."""
        return self.headers.get("Host") == f"{LOOPBACK}:{self.server.server_port}"

    def same_origin(self) -> bool:
        return self.headers.get("Origin") == f"http://{LOOPBACK}:{self.server.server_port}"

    @staticmethod
    def token_matches(supplied: str | None, token: str) -> bool:
        return secrets.compare_digest((supplied or "").encode(), token.encode())

    def route(self) -> str:
        return urlsplit(self.path).path

    def query(self, name: str, default: str = "") -> str:
        return parse_qs(urlsplit(self.path).query).get(name, [default])[0]

    def read_json(self, limit: int) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= limit or self.headers.get("Content-Type") != "application/json":
            raise ValueError("Invalid request size or content type")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("Invalid request")
        return value


def list_folders(path: str) -> dict:
    """Visible sub-folders of `path`, for a folder picker. Names only, no files."""
    folder = Path(path).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("Not a directory")
    entries = sorted(
        (x for x in folder.iterdir() if not x.name.startswith(".") and x.is_dir()),
        key=lambda x: x.name.lower(),
    )
    return {
        "path": str(folder),
        "parent": str(folder.parent) if folder.parent != folder else "",
        "directories": [{"name": x.name, "path": str(x)} for x in entries],
    }


def write_private_json(path: Path, value: dict) -> None:
    """Write owner-only JSON atomically, so a reader never sees a partial file."""
    temp = path.with_name(f"{path.name}.{secrets.token_hex(6)}.tmp")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
