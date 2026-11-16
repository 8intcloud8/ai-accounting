#!/usr/bin/env python3
"""BAS: one window with the Codex chat on the left and the BAS steps on the right.

The steps panel reads the accounting database read-only. Everything stays on this
computer (127.0.0.1, with a random token). Opens in its own window when pywebview
is installed, otherwise in the default browser. Closing the window stops Codex.
"""

import argparse
import json
import queue
import secrets
import sqlite3
import sys
import threading
import webbrowser
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "accounting_core"))
sys.path.insert(0, str(HERE))
import accounting_store  # noqa: E402
import bas_dashboard  # noqa: E402
import check_environment  # noqa: E402
import local_server  # noqa: E402
import workspace_instructions  # noqa: E402
from codex_chat import Codex  # noqa: E402
from local_server import LocalHandler  # noqa: E402

PAGE = (HERE / "page.html").read_text()
SELECTOR = "accounting-workspace.json"
SANDBOX_BLOCKED = "Cannot open the BAS app: this computer blocked the local port."


def default_period(today=None):
    """The most recently ended BAS quarter: the one being prepared and lodged next."""
    today = today or date.today()
    first_of_quarter = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
    end = first_of_quarter - timedelta(days=1)
    start = date(end.year, end.month - 2, 1)
    return start.isoformat(), end.isoformat()


def default_workspace():
    selector = Path(check_environment.codex_home()) / SELECTOR
    try:
        return Path(json.loads(selector.read_text())["workspace"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit("No accounting workspace is set up yet. Open Codex and ask: "
                         "prepare my accounting period.") from error


def create_server(codex, db, start, end, port=0):
    token = secrets.token_urlsafe(32)
    bas_dashboard.snapshot(db, start, end)  # Fail fast if the workspace is not set up.

    class Handler(LocalHandler):
        def authorised(self, supplied):
            return self.local_host() and self.token_matches(supplied, token)

        def do_GET(self):
            route = self.route()
            if route == "/" and self.authorised(self.query("token")):
                return self.reply(200, PAGE.replace("__TOKEN__", json.dumps(token)), "text/html; charset=utf-8")
            if route == "/api/status" and self.authorised(self.headers.get("X-App-Token")):
                try:
                    data = bas_dashboard.snapshot(db, start, end)
                except Exception as error:  # noqa: BLE001 - shown to the user, never raised
                    return self.reply(503, json.dumps({"error": str(error)}))
                return self.reply(200, json.dumps({**data, "working": codex.working}))
            if route == "/api/history" and self.authorised(self.headers.get("X-App-Token")):
                return self.reply(200, json.dumps({"history": codex.history, "working": codex.working}))
            if route == "/api/events" and self.authorised(self.query("token")):
                return self.stream()
            self.send_error(403 if route.startswith("/api") or route == "/" else 404)

        def do_POST(self):
            if not (self.same_origin() and self.authorised(self.headers.get("X-App-Token"))):
                return self.send_error(403)
            try:
                body = self.read_json(20_000)
                if self.route() == "/api/send":
                    text = str(body.get("text", "")).strip()
                    if not text:
                        raise ValueError("Type a message first.")
                    codex.send(text)
                elif self.route() == "/api/stop":
                    codex.stop()
                else:
                    return self.send_error(404)
                self.reply(200, json.dumps({"ok": True}))
            except (ValueError, RuntimeError, TimeoutError) as error:
                self.reply(400, json.dumps({"error": str(error)}))

        def stream(self):
            events = queue.Queue()
            codex.listeners.add(events)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while not getattr(self.server, "closing", False):
                    try:
                        payload = f"data: {json.dumps(events.get(timeout=15))}\n\n"
                    except queue.Empty:
                        payload = ": keep-alive\n\n"
                    self.wfile.write(payload.encode())
                    self.wfile.flush()
            except OSError:
                pass
            finally:
                codex.listeners.discard(events)

    server = local_server.bind_loopback(Handler, port, SANDBOX_BLOCKED)
    server.app_url = local_server.url(server, token)
    return server


def open_window(url):
    """Show the app in its own window and return when it closes. False if no pywebview."""
    check_environment.activate()
    try:
        import webview
    except ImportError:
        return False
    webview.create_window("BAS", url, width=1320, height=860, min_size=(900, 600))
    webview.start()
    return True


def codex_command():
    codex = check_environment.find_codex()
    if not codex:
        raise SystemExit("Codex is not installed. Install the ChatGPT desktop app or the Codex CLI.")
    return [codex, "app-server"]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Defaults to the workspace Codex uses")
    parser.add_argument("--start", help="Period start (YYYY-MM-DD); defaults to the last BAS quarter")
    parser.add_argument("--end", help="Period end (YYYY-MM-DD)")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--browser", action="store_true", help="Open in the default browser, not a window")
    parser.add_argument("--no-open", action="store_true", help="Only print the address")
    args = parser.parse_args(argv)
    if bool(args.start) != bool(args.end):
        parser.error("Give both --start and --end, or neither")
    if not args.start:
        args.start, args.end = default_period()
    args.workspace = (args.workspace or default_workspace()).expanduser().resolve()
    return args


def main(argv=None):
    args = parse_args(argv)
    db = args.workspace / "db/accounting.db"
    if not db.exists():
        raise SystemExit(f"No accounting database in {args.workspace}. Open Codex and set up the workspace first.")
    # Bring an older database's tables up to date (as any accounting command does), so the
    # read-only steps panel can read it. Changes no records.
    accounting_store.connect(db).close()
    workspace_instructions.ensure(args.workspace)
    codex = Codex(codex_command(), args.workspace, f"{args.start}_{args.end}")
    server = None
    try:
        try:
            server = create_server(codex, db, args.start, args.end, args.port)
        except (ValueError, OSError, sqlite3.Error) as error:
            raise SystemExit(f"Cannot show the BAS steps for this workspace: {error}") from error
        threading.Thread(target=server.serve_forever, daemon=True).start()
        shown = {"app_url": server.app_url} if args.no_open else {}  # Keep the token out of logs.
        print(json.dumps({**shown, "workspace": str(args.workspace),
                          "period": [args.start, args.end], "resumed": codex.resumed}), flush=True)
        if args.no_open or args.browser or not open_window(server.app_url):
            if not args.no_open:
                webbrowser.open(server.app_url)
            threading.Event().wait()  # Serve until Ctrl-C.
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.closing = True
            server.shutdown()
            server.server_close()
        codex.close()


if __name__ == "__main__":
    main()
