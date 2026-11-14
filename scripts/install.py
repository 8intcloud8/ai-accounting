#!/usr/bin/env python3
"""Install the AI Accounting suite into Codex; configure a local workspace.

Requires Python 3.11+. With --dependencies, installs isolated Python packages and
builds Gmail plugins using an available Node/npm. No database server is needed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
import venv
from pathlib import Path


LOCAL_SERVER_QUESTION = (
    "\nTurn on the buttons in the review pages (Save selection, Choose folder)?\n"
    "Without them you copy a line from the page and paste it into the chat.\n"
    "Turning them on lets commands Codex runs use the internet. You can turn it off later.\n"
    "Turn on? [y/N] "
)


def local_server_choice(choice, codex_home):
    """Apply the user's answer. Never turn the setting on without a yes."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))
    import enable_local_server

    current = enable_local_server.status(codex_home)
    if choice == "ask":
        if current["on"] or current["asked"] or not sys.stdin.isatty():
            return current
        choice = "yes" if input(LOCAL_SERVER_QUESTION).strip().lower() in ("y", "yes") else "no"
    if choice == "yes":
        return enable_local_server.apply(codex_home, True)
    enable_local_server.record_asked(codex_home)
    return enable_local_server.status(codex_home)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument(
        "--profile",
        type=Path,
        help="JSON business profile; omit when already configured",
    )
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--dependencies", action="store_true")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Omit Gmail search/save plugins and Node requirement",
    )
    parser.add_argument(
        "--register-only",
        action="store_true",
        help="Write configuration only for packaging checks; does not install plugins",
    )
    parser.add_argument(
        "--local-server",
        choices=("ask", "yes", "no"),
        default="ask",
        help="Turn on buttons in the local review pages (lets Codex commands use the network)",
    )
    args = parser.parse_args()
    args.codex_home = args.codex_home.expanduser().resolve()
    codex = shutil.which("codex")
    if not args.register_only and not codex:
        parser.error(
            "Codex CLI is required to install plugins. Install Codex, then rerun."
        )
    root = Path(__file__).resolve().parents[1]
    workspace = args.workspace.expanduser().resolve()
    database = workspace / "db/accounting.db"
    if not database.exists() and not args.profile:
        parser.error("--profile required for a new workspace")
    if args.profile:
        json.loads(args.profile.read_text())
    config = args.codex_home / "config.toml"
    old = config.read_text() if config.exists() else ""
    tomllib.loads(old)
    marketplace = {
        "plugins": [
            json.loads(p.read_text())
            for p in sorted((root / "plugins").glob("*/.codex-plugin/plugin.json"))
        ]
    }
    plugins = [
        e["name"]
        for e in marketplace["plugins"]
        if not (args.local_only and e["name"] in ("search-email-invoices", "save-invoices"))
    ]
    # Validate existing choices before native installation or configuration changes.
    updated = old
    existing = tomllib.loads(old)
    if "ai-accounting" not in existing.get("marketplaces", {}):
        updated += (
            '\n[marketplaces.ai-accounting]\nsource_type = "local"\nsource = '
            + json.dumps(str(root))
            + "\n"
        )
    elif existing["marketplaces"]["ai-accounting"].get("source") != str(root):
        raise ValueError(
            "Existing ai-accounting marketplace points elsewhere; update that install in place"
        )
    for name in plugins:
        key = name + "@ai-accounting"
        if key not in existing.get("plugins", {}):
            updated += "\n[plugins." + json.dumps(key) + "]\nenabled = true\n"
        elif not existing["plugins"][key].get("enabled"):
            raise ValueError(f"{key} is disabled; enable explicitly in Codex")
    tomllib.loads(updated)
    # Synchronize generated shared UI styles before npm compiles the email UI.
    subprocess.run([sys.executable, str(root / "scripts/build_release.py")], check=True)
    if args.dependencies:
        env = root / ".venv"
        venv.EnvBuilder(with_pip=True).create(env)
        python = env / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )
        subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(root / "requirements.txt")],
            check=True,
        )
        if not args.local_only:
            npm = shutil.which("npm")
            if not npm:
                raise RuntimeError(
                    "Node/npm required for Gmail plugins; use --local-only for local files"
                )
            for name in ("search-email-invoices", "save-invoices"):
                subprocess.run(
                    [npm, "ci"], cwd=root / "plugins" / name / "mcp-server", check=True
                )
                subprocess.run(
                    [npm, "run", "build"],
                    cwd=root / "plugins" / name / "mcp-server",
                    check=True,
                )
    if args.profile:
        subprocess.run(
            [
                sys.executable,
                str(root / "accounting_core/accounting_store.py"),
                "--db",
                str(database),
                "setup-accounting",
                "--request",
                str(args.profile),
            ],
            check=True,
        )
    config.parent.mkdir(parents=True, exist_ok=True)
    # Write the host-specific workspace selector before any plugin is enabled
    # below. Plugins resolve this file before falling back to the old/default
    # database, so a failure partway through plugin-enabling must never leave
    # an already-enabled plugin pointing at the wrong workspace.
    selector = args.codex_home / "accounting-workspace.json"
    selector.parent.mkdir(parents=True, exist_ok=True)
    selector_temp = selector.with_suffix(".tmp")
    selector_temp.write_text(json.dumps({"workspace": str(workspace)}) + "\n")
    selector_temp.chmod(0o600)
    selector_temp.replace(selector)
    # Every workspace set up here is offered when a new chat asks which one to use.
    registry = args.codex_home / "accounting-workspaces.json"
    known = json.loads(registry.read_text()) if registry.exists() else {"workspaces": []}
    if str(workspace) not in known["workspaces"]:
        known["workspaces"].append(str(workspace))
        registry_temp = registry.with_suffix(".tmp")
        registry_temp.write_text(json.dumps(known, indent=2) + "\n")
        registry_temp.replace(registry)
    if args.register_only:
        temp = config.with_suffix(".accounting.tmp")
        temp.write_text(updated)
        temp.replace(config)
    else:
        environment = dict(os.environ, CODEX_HOME=str(args.codex_home))

        def run_codex(*arguments):
            result = subprocess.run(
                [codex, "plugin", *arguments, "--json"],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads(result.stdout)

        run_codex("marketplace", "add", str(root))
        for name in plugins:
            installed = run_codex("add", name + "@ai-accounting")
            location = Path(installed["installedPath"])
            skills = list((location / "skills").glob("*/SKILL.md"))
            if len(skills) != 1:
                raise RuntimeError(
                    f"{name}: expected one installed skill, found {len(skills)}"
                )
        discovered = run_codex("list", "--marketplace", "ai-accounting")
        enabled = {
            item["name"]
            for item in discovered["installed"]
            if item.get("installed") and item.get("enabled")
        }
        missing = set(plugins) - enabled
        if missing:
            raise RuntimeError(
                f"Plugins not enabled after installation: {sorted(missing)}"
            )
    buttons = local_server_choice(args.local_server, args.codex_home)
    print(
        json.dumps(
            {
                "local_server": buttons["on"],
                (
                    "registered_plugins" if args.register_only else "installed_plugins"
                ): plugins,
                "workspace": str(workspace),
                "next": (
                    "Configuration written only; rerun without --register-only to install."
                    if args.register_only
                    else ("Quit and reopen Codex. " if buttons.get("restart_codex") else "")
                    + "Open a new Codex chat. Ask: prepare my accounting period."
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
