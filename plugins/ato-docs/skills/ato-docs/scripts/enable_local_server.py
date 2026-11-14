#!/usr/bin/env python3
"""Turn the buttons in the local review pages on or off.

The buttons (Save selection, Choose folder, quarantine) need a small server on
this computer. Codex blocks it unless `network_access = true` is set under
`[sandbox_workspace_write]` in its config, which also lets every command Codex
runs use the network. This is the user's choice, so it is only changed on request.
"""

import argparse
import json
import os
import re
import tomllib
from pathlib import Path

TABLE = "sandbox_workspace_write"
KEY = "network_access"
HEADER = re.compile(rf"^\[{TABLE}\][ \t]*(#.*)?$", re.MULTILINE)
NEXT_TABLE = re.compile(r"^\[", re.MULTILINE)
KEY_LINE = re.compile(rf"^{KEY}[ \t]*=.*$", re.MULTILINE)
ASKED_FILE = "accounting-local-server.json"
HAND_EDIT = (
    "Could not change the Codex config automatically. Add these two lines to "
    "{path} by hand:\n\n[sandbox_workspace_write]\nnetwork_access = true\n"
)


def codex_home(value: Path | None = None) -> Path:
    return (value or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))).expanduser()


def is_on(text: str) -> bool:
    return tomllib.loads(text).get(TABLE, {}).get(KEY) is True


def with_setting(text: str, on: bool) -> str:
    """Return the config text with the setting changed and nothing else touched."""
    if is_on(text) == on:
        return text
    line = f"{KEY} = {'true' if on else 'false'}"
    header = HEADER.search(text)
    if not header:
        if TABLE in tomllib.loads(text):
            raise ValueError("unsupported layout")  # Inline or dotted table.
        updated = text.rstrip("\n") + f"\n\n[{TABLE}]\n{line}\n" if text.strip() else f"[{TABLE}]\n{line}\n"
    else:
        following = NEXT_TABLE.search(text, header.end())
        end = following.start() if following else len(text)
        body = text[header.end():end]
        body = KEY_LINE.sub(line, body, count=1) if KEY_LINE.search(body) else f"\n{line}" + body
        updated = text[:header.end()] + body + text[end:]
    if is_on(updated) != on:
        raise ValueError("unsupported layout")
    return updated


def status(home: Path) -> dict:
    config = home / "config.toml"
    text = config.read_text() if config.exists() else ""
    return {"on": is_on(text), "asked": (home / ASKED_FILE).exists(), "config": str(config)}


def record_asked(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / ASKED_FILE).write_text(json.dumps({"asked": True}) + "\n")


def apply(home: Path, on: bool) -> dict:
    config = home / "config.toml"
    text = config.read_text() if config.exists() else ""
    try:
        updated = with_setting(text, on)
    except ValueError as error:
        raise SystemExit(HAND_EDIT.format(path=config)) from error
    if updated != text:
        home.mkdir(parents=True, exist_ok=True)
        temp = config.with_suffix(".local-server.tmp")
        temp.write_text(updated)
        temp.replace(config)
    record_asked(home)
    return {**status(home), "changed": updated != text, "restart_codex": updated != text}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "on", "off", "decline"))
    parser.add_argument("--codex-home", type=Path)
    args = parser.parse_args()
    home = codex_home(args.codex_home)
    if args.action == "status":
        result = status(home)
    elif args.action == "decline":
        record_asked(home)
        result = status(home)
    else:
        result = apply(home, args.action == "on")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
