"""Serve one invoice checklist and its authenticated, read-only folder picker."""
import argparse
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlsplit

SANDBOX_BLOCKED = (
    "Cannot serve the checklist: this host blocked the loopback port.\n"
    "Codex sandboxes shell commands and denies all network access by default, "
    "including 127.0.0.1.\n"
    "To enable it, add to ~/.codex/config.toml and restart Codex:\n"
    "\n"
    "    [sandbox_workspace_write]\n"
    "    network_access = true\n"
    "\n"
    "Until then the rendered index.html still opens directly in a browser, with "
    "selection, filtering and Copy save request working; only Choose folder needs "
    "this server. Report the blocker and give the file path; do not claim the "
    "picker was verified."
)


def bind_loopback(handler, port):
    """Bind loopback, or fail with the sandbox remedy instead of a bare EPERM."""
    try:
        return ThreadingHTTPServer(("127.0.0.1", port), handler)
    except PermissionError as error:
        raise SystemExit(SANDBOX_BLOCKED) from error
    except OSError as error:
        if error.errno in (errno.EPERM, errno.EACCES, errno.EAFNOSUPPORT):
            raise SystemExit(SANDBOX_BLOCKED) from error
        if error.errno == errno.EADDRINUSE:
            raise SystemExit(
                f"Port {port} is already in use, most likely by a checklist server "
                "left running by an earlier run. Omit --port to take any free port; "
                "never reuse the old server's URL, because it may serve a previous "
                "run's invoices."
            ) from error
        raise


TOKEN_PATTERN = re.compile(rb'"pickerToken":\s*"([A-Za-z0-9_-]+)"')


def read_report(report):
    """Re-read per request so a re-rendered checklist and its picker token take
    effect immediately. Caching them at startup made a surviving server serve a
    previous run's invoices with a stale token, which the picker then rejected."""
    page = report.read_bytes()
    token = TOKEN_PATTERN.search(page)
    if not token:
        raise ValueError('Render the checklist with render_checklist.py first')
    return page, token[1].decode()


def make_handler(report_dir):
    report = Path(report_dir).resolve() / 'index.html'
    read_report(report)  # Fail fast on an unrendered report.

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                self.send_error(403)
                return
            try:
                page, token = read_report(report)
            except (OSError, ValueError):
                self.send_error(503, 'Checklist report is unavailable; re-render it')
                return
            if url.path in ('/', '/index.html'):
                payload, kind = page, 'text/html; charset=utf-8'
            elif url.path == '/api/folders':
                if not secrets.compare_digest(self.headers.get('X-Folder-Picker', ''), token):
                    self.send_error(403)
                    return
                try:
                    folder = Path(parse_qs(url.query).get('path', [str(Path.home())])[0]).expanduser().resolve(strict=True)
                    if not folder.is_dir():
                        raise ValueError('Not a directory')
                    entries = sorted((x for x in folder.iterdir() if not x.name.startswith('.') and x.is_dir()), key=lambda x: x.name.lower())
                    payload = json.dumps({'path': str(folder), 'parent': str(folder.parent) if folder.parent != folder else '', 'directories': [{'name': x.name, 'path': str(x)} for x in entries]}).encode()
                    kind = 'application/json'
                except (OSError, ValueError):
                    self.send_error(400, 'Cannot open folder')
                    return
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_dir', type=Path)
    # Default to an ephemeral port: a fixed one collided with a server left
    # running by an earlier run, so each run behaved differently.
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = bind_loopback(make_handler(args.report_dir), args.port)
    print(json.dumps({'checklist_url': f'http://127.0.0.1:{server.server_port}/'}), flush=True)
    server.serve_forever()
