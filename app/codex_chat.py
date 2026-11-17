"""One Codex conversation for the BAS app, over the `codex app-server` stdio protocol.

The chat is Codex itself, so it uses the user's ChatGPT sign-in and the installed
accounting plugins. The conversation's thread id is saved inside the workspace
(owner-only), so reopening the app continues the same chat for that BAS period.
"""

import json
import secrets
import subprocess
import threading
from pathlib import Path

import local_server

INSTRUCTIONS = (
    "The user is in the BAS app. The BAS steps are shown beside this chat and update as you "
    "work, so do not repeat the full step list unless asked. Write for a non-technical business "
    "owner: short, plain sentences. After every change, correction or answer, even a short one, "
    "run workflow-status for the period and end with one question that starts the first open step, "
    "for example: \"Shall I classify the 275 uncategorised transactions now?\" Use next_step.end_your_reply_with when a command returns it. If the user said to keep going, start it. "
    "Never end with only a summary of what changed, or with a promise to continue: do the work or ask."
)
WORKING = {"commandExecution": "Checking the books", "reasoning": "Thinking",
           "fileChange": "Updating files", "mcpToolCall": "Using a tool", "webSearch": "Searching the ATO site"}
STATE_FILE = "bas-app.json"


class ThreadStore:
    """Saved thread ids per BAS period, in an owner-only file in the workspace's db/ folder."""

    def __init__(self, workspace):
        self.path = Path(workspace) / "db" / STATE_FILE

    def _load(self):
        try:
            value = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        threads = value.get("threads") if isinstance(value, dict) else None
        return {k: v for k, v in threads.items() if isinstance(v, str)} if isinstance(threads, dict) else {}

    def get(self, key):
        return self._load().get(key)

    def set(self, key, thread_id):
        threads = {**self._load(), key: thread_id}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        local_server.write_private_json(self.path, {"threads": threads})


def history_from_turns(turns):
    """The chat messages (user and assistant text only) from a thread's saved turns."""
    history = []
    for turn in turns or []:
        for item in turn.get("items") or []:
            if item.get("type") == "userMessage":
                text = "\n".join(c.get("text", "") for c in item.get("content") or [] if c.get("type") == "text")
                role = "user"
            elif item.get("type") == "agentMessage":
                text, role = item.get("text", ""), "assistant"
            else:
                continue
            if text.strip():
                history.append({"id": str(item.get("id") or secrets.token_hex(4)), "role": role, "text": text})
    return history


class Codex:
    """Drives one app-server child process. `command` is the app-server argv."""

    def __init__(self, command, workspace, period_key, store=None, timeout=120):
        self.workspace = str(workspace)
        self.period_key = period_key
        self.store = store or ThreadStore(workspace)
        self.timeout = timeout
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.lock = threading.Lock()
        self.next_id = 0
        self.pending = {}
        self.listeners = set()
        self.history = []  # [{"id", "role", "text"}]
        self.turn_id = None
        self.finished = set()
        self.busy = False
        self.resumed = False
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.call("initialize", {"clientInfo": {"name": "bas_app", "title": "BAS", "version": "1.0"}})
            self._write({"method": "initialized", "params": {}})
            self.thread_id = self._open_thread()
        except BaseException:
            self.close()
            raise

    def _thread_settings(self):
        return {"cwd": self.workspace, "sandbox": "workspace-write", "approvalPolicy": "never",
                "developerInstructions": INSTRUCTIONS}

    def _open_thread(self):
        saved = self.store.get(self.period_key)
        if saved:
            try:
                result = self.call("thread/resume", {"threadId": saved, **self._thread_settings()})
                self.history = history_from_turns(result["thread"].get("turns"))
                self.resumed = True
                return result["thread"]["id"]
            except (RuntimeError, TimeoutError, KeyError, TypeError):
                pass  # Gone or unreadable: start a fresh chat for this period.
        thread_id = self.call("thread/start", self._thread_settings())["thread"]["id"]
        self.store.set(self.period_key, thread_id)
        return thread_id

    def _write(self, message):
        with self.lock:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()

    def call(self, method, params, timeout=None):
        with self.lock:
            self.next_id += 1
            ident = self.next_id
        done = {"event": threading.Event()}
        self.pending[ident] = done
        try:
            self._write({"id": ident, "method": method, "params": params})
        except (OSError, ValueError) as error:
            self.pending.pop(ident, None)
            raise RuntimeError("Codex stopped. Close and reopen the app.") from error
        if not done["event"].wait(timeout or self.timeout):
            self.pending.pop(ident, None)
            raise TimeoutError(f"Codex did not answer {method}")
        if "error" in done["reply"]:
            raise RuntimeError(done["reply"]["error"].get("message", "Codex error"))
        return done["reply"].get("result") or {}

    @property
    def working(self):
        return bool(self.turn_id or self.busy)

    def send(self, text):
        if self.working:
            raise RuntimeError("Codex is still working. Wait, or press Stop.")
        self.busy = True
        try:
            self._remember("user", text)
            result = self.call("turn/start", {"threadId": self.thread_id, "input": [{"type": "text", "text": text}]})
            started = (result.get("turn") or {}).get("id")
            if started and started not in self.finished:  # Its notifications may arrive first.
                self.turn_id = started
        finally:
            self.busy = False

    def stop(self):
        if self.turn_id:
            self.call("turn/interrupt", {"threadId": self.thread_id, "turnId": self.turn_id})

    def close(self):
        """Stop the app-server child. Safe to call more than once."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def _remember(self, role, text, ident=None):
        entry = {"id": ident or secrets.token_hex(4), "role": role, "text": text}
        self.history.append(entry)
        self._publish({"type": "message", **entry})

    def _publish(self, event):
        for listener in list(self.listeners):
            listener.put(event)

    def _read(self):
        for line in self.proc.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            method, ident = message.get("method"), message.get("id")
            if ident is not None and not method:
                waiter = self.pending.pop(ident, None)
                if waiter:
                    waiter["reply"] = message
                    waiter["event"].set()
            elif ident is not None:
                # approvalPolicy is "never", so requests here are rare; decline rather than hang.
                self._write({"id": ident, "error": {"code": -32601, "message": "Not supported in the BAS app"}})
            else:
                self._notify(method, message.get("params") or {})
        self.turn_id = None
        for waiter in list(self.pending.values()):
            waiter["reply"] = {"error": {"message": "Codex stopped. Close and reopen the app."}}
            waiter["event"].set()
        self._publish({"type": "error", "text": "Codex stopped. Close and reopen the app."})

    def _notify(self, method, params):
        if method == "turn/started":
            self.turn_id = (params.get("turn") or {}).get("id") or self.turn_id
            self._publish({"type": "turn", "state": "running"})
        elif method == "turn/completed":
            self.finished.add((params.get("turn") or {}).get("id"))
            self.turn_id = None
            self._publish({"type": "turn", "state": (params.get("turn") or {}).get("status", "completed")})
        elif method == "item/agentMessage/delta":
            item, delta = str(params.get("itemId")), str(params.get("delta", ""))
            entry = next((h for h in self.history if h["id"] == item), None)
            if entry is None:
                entry = {"id": item, "role": "assistant", "text": ""}
                self.history.append(entry)
            entry["text"] += delta
            self._publish({"type": "delta", "id": item, "text": delta})
        elif method == "item/started":
            label = WORKING.get((params.get("item") or {}).get("type"))
            if label:
                self._publish({"type": "working", "text": label})
        elif method == "item/completed" and (params.get("item") or {}).get("type") in WORKING:
            self._publish({"type": "changed"})  # The books may have changed: refresh the steps.
        elif method == "error":
            self._publish({"type": "error", "text": (params.get("error") or {}).get("message", "Codex reported an error")})
