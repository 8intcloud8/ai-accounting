"""Serve one invoice checklist: its folder picker and its Save selection button."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re

import local_server
from local_server import LocalHandler

SANDBOX_BLOCKED = local_server.sandbox_blocked(
    "the checklist server",
    "Until then the rendered index.html still opens directly in a browser, with "
    "selection, filtering and Copy save request working; only Choose folder and "
    "Save selection need this server. Open the file instead; do not claim the "
    "server-only controls were verified.",
)
PORT_BUSY = (
    "Port {port} is already in use, most likely by a checklist server left running "
    "by an earlier run. Omit --port to take any free port; never reuse the old "
    "server's URL, because it may serve a previous run's invoices."
)
SELECTION_FILE = "selection.json"
MAX_SELECTION_BYTES = 256 * 1024
TOKEN_PATTERN = re.compile(rb'"pickerToken":\s*"([A-Za-z0-9_-]+)"')
BILL_PATTERN = re.compile(r'class="bill"[^>]*? value="([^"]+)" data-message="([^"]*)"')
CONFIG_MARKER = "const config="


def bind_loopback(handler, port):
    return local_server.bind_loopback(
        handler, port, SANDBOX_BLOCKED, PORT_BUSY.format(port=port)
    )


def read_report(report):
    """Re-read per request so a re-rendered checklist and its picker token take
    effect immediately. Caching them at startup made a surviving server serve a
    previous run's invoices with a stale token, which the picker then rejected."""
    page = report.read_bytes()
    token = TOKEN_PATTERN.search(page)
    if not token:
        raise ValueError('Render the checklist with render_checklist.py first')
    return page, token[1].decode()


def selection(page, request):
    """Validate a Save selection request against the page it came from."""
    text = page.decode()
    bills = dict(BILL_PATTERN.findall(text))
    config, _end = json.JSONDecoder().raw_decode(text, text.index(CONFIG_MARKER) + len(CONFIG_MARKER))
    root = request.get("root")
    chosen = request.get("threadIds")
    if not isinstance(root, str) or not root.strip() or len(root) > 4096 or not Path(root).expanduser().is_absolute():
        raise ValueError("Enter the full folder path to save into")
    if not isinstance(chosen, list) or not chosen or len(set(chosen)) != len(chosen):
        raise ValueError("Select at least one invoice")
    if any(not isinstance(x, str) or x not in bills for x in chosen):
        raise ValueError("Selection does not match this checklist; reload the page")
    return {
        "root_folder": str(Path(root).expanduser()),
        "category": config["category"],
        "date_from": config["from"],
        "date_to": config["to"],
        "threads": [{"threadId": x, "messageId": bills[x]} for x in chosen],
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def make_handler(report_dir):
    report_dir = Path(report_dir).resolve()
    report = report_dir / 'index.html'
    read_report(report)  # Fail fast on an unrendered report.

    class Handler(LocalHandler):
        csp = local_server.DEFAULT_CSP.replace("frame-ancestors 'none'", "frame-ancestors 'self'")

        def current(self):
            """The page and its token, or None after answering with the reason."""
            if not self.local_host():
                self.send_error(403)
                return None
            try:
                return read_report(report)
            except (OSError, ValueError):
                self.send_error(503, 'Checklist report is unavailable; re-render it')
                return None

        def do_GET(self):
            loaded = self.current()
            if not loaded:
                return
            page, token = loaded
            route = self.route()
            if route in ('/', '/index.html'):
                self.reply(200, page, 'text/html; charset=utf-8')
            elif route == '/api/folders':
                if not self.token_matches(self.headers.get('X-Folder-Picker'), token):
                    self.send_error(403)
                    return
                try:
                    folders = local_server.list_folders(self.query('path', str(Path.home())))
                except (OSError, ValueError):
                    self.send_error(400, 'Cannot open folder')
                    return
                self.reply(200, json.dumps(folders))
            else:
                self.send_error(404)

        def do_POST(self):
            loaded = self.current()
            if not loaded:
                return
            page, token = loaded
            if not self.same_origin() or not self.token_matches(self.headers.get('X-Folder-Picker'), token):
                self.send_error(403)
                return
            if self.route() != '/api/selection':
                self.send_error(404)
                return
            try:
                chosen = selection(page, self.read_json(MAX_SELECTION_BYTES))
                local_server.write_private_json(report_dir / SELECTION_FILE, chosen)
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.reply(400, json.dumps({'error': str(error)}))
                return
            self.reply(201, json.dumps({'saved': len(chosen['threads'])}))

    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_dir', type=Path)
    # Default to an ephemeral port: a fixed one collided with a server left
    # running by an earlier run, so each run behaved differently.
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = bind_loopback(make_handler(args.report_dir), args.port)
    print(json.dumps({
        'checklist_url': local_server.url(server),
        'selection_file': str(Path(args.report_dir).resolve() / SELECTION_FILE),
    }), flush=True)
    server.serve_forever()
