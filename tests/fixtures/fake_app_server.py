#!/usr/bin/env python3
"""Stand-in for `codex app-server`: just enough JSON-RPC to drive the BAS app in tests.

Thread "known-thread" can be resumed and has one saved exchange; any other id fails
to resume. Every request is appended to the file named by FAKE_APP_SERVER_LOG.
"""

import json
import os
import sys

LOG = os.environ.get("FAKE_APP_SERVER_LOG")
started = 0


def say(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    message = json.loads(line)
    method, ident, params = message.get("method"), message.get("id"), message.get("params", {})
    if LOG:
        with open(LOG, "a") as log:
            log.write(json.dumps({"method": method, "params": params}) + "\n")
    if ident is None:
        continue
    if method == "initialize":
        say({"id": ident, "result": {}})
    elif method == "thread/start":
        started += 1
        say({"id": ident, "result": {"thread": {"id": f"new-thread-{started}", "turns": []}}})
    elif method == "thread/resume":
        if params.get("threadId") != "known-thread":
            say({"id": ident, "error": {"code": -32600, "message": "no rollout found"}})
            continue
        turns = [{"id": "turn-0", "items": [
            {"type": "userMessage", "id": "u0", "content": [{"type": "text", "text": "Hi <b>there</b>"}]},
            {"type": "reasoning", "id": "r0"},
            {"type": "agentMessage", "id": "a0", "text": "Hello again."},
        ]}]
        say({"id": ident, "result": {"thread": {"id": "known-thread", "turns": turns}}})
    elif method == "turn/start":
        say({"id": ident, "result": {"turn": {"id": "turn-1"}}})
        say({"method": "turn/started", "params": {"turn": {"id": "turn-1"}}})
        for delta in ("Your BAS ", "is on track."):
            say({"method": "item/agentMessage/delta", "params": {"itemId": "a1", "delta": delta}})
        say({"method": "turn/completed", "params": {"turn": {"id": "turn-1", "status": "completed"}}})
    else:
        say({"id": ident, "result": {}})
