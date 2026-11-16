#!/usr/bin/env python3
"""Install the AI Accounting suite into Codex from this checkout and set up a workspace.

For maintainers. Users add the repository as a plugin source in Codex Desktop instead.
Requires Python 3.11+. With --dependencies, installs the Python packages into the
private folder the setup check uses and builds the Gmail plugins with Node/npm.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "accounting_core"))
import check_environment  # noqa: E402
import enable_local_server  # noqa: E402
import workspace_instructions  # noqa: E402

sys.path.insert(0, str(ROOT / "app"))

MARKETPLACE = "ai-accounting"
EMAIL_PLUGINS = ("search-email-invoices", "save-invoices")
LOCAL_SERVER_QUESTION = (
    "\nTurn on the buttons in the review pages (Save selection, Choose folder)?\n"
    "Without them you copy a line from the page and paste it into the chat.\n"
    "Turning them on lets commands Codex runs use the internet. You can turn it off later.\n"
    "Turn on? [y/N] "
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--profile", type=Path, help="JSON business profile; omit when already configured")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--dependencies", action="store_true",
                        help="Install Python packages and build the Gmail plugins")
    parser.add_argument("--local-only", action="store_true",
                        help="Omit Gmail search/save plugins and the Node requirement")
    parser.add_argument("--register-only", action="store_true",
                        help="Write configuration only for packaging checks; does not install plugins")
    parser.add_argument("--local-server", choices=("ask", "yes", "no"), default="ask",
                        help="Turn on buttons in the local review pages (lets Codex commands use the network)")
    parser.add_argument("--desktop-app", type=Path, nargs="?", const=Path.home() / "Applications",
                        metavar="FOLDER", help="Also make the double-clickable BAS app (default ~/Applications)")
    args = parser.parse_args()
    args.codex_home = args.codex_home.expanduser().resolve()
    args.workspace = args.workspace.expanduser().resolve()
    args.codex = check_environment.find_codex()
    if not args.register_only and not args.codex:
        parser.error("Codex is required: install Codex Desktop or the Codex CLI, then rerun.")
    if not (args.workspace / "db/accounting.db").exists() and not args.profile:
        parser.error("--profile required for a new workspace")
    if args.profile:
        json.loads(args.profile.read_text())
    return args


def plugin_names(local_only):
    names = [
        json.loads(p.read_text())["name"]
        for p in sorted((ROOT / "plugins").glob("*/.codex-plugin/plugin.json"))
    ]
    return [n for n in names if not (local_only and n in EMAIL_PLUGINS)]


def planned_config(config, plugins):
    """Codex config with the marketplace and plugins added. Refuses conflicting installs."""
    old = config.read_text() if config.exists() else ""
    existing = tomllib.loads(old)
    updated = old
    source = existing.get("marketplaces", {}).get(MARKETPLACE, {}).get("source")
    if source is None:
        updated += f'\n[marketplaces.{MARKETPLACE}]\nsource_type = "local"\nsource = {json.dumps(str(ROOT))}\n'
    elif source != str(ROOT):
        raise ValueError(f"Existing {MARKETPLACE} marketplace points elsewhere; update that install in place")
    for name in plugins:
        key = f"{name}@{MARKETPLACE}"
        entry = existing.get("plugins", {}).get(key)
        if entry is None:
            updated += f"\n[plugins.{json.dumps(key)}]\nenabled = true\n"
        elif not entry.get("enabled"):
            raise ValueError(f"{key} is disabled; enable explicitly in Codex")
    tomllib.loads(updated)
    return updated


def install_dependencies(codex_home, local_only):
    os.environ["CODEX_HOME"] = str(codex_home)
    check_environment.install()
    if local_only:
        return
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("Node/npm required for Gmail plugins; use --local-only for local files")
    for name in EMAIL_PLUGINS:
        server = ROOT / "plugins" / name / "mcp-server"
        subprocess.run([npm, "ci"], cwd=server, check=True)
        subprocess.run([npm, "run", "build"], cwd=server, check=True)


def write_json(path, value, private=False):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    if private:
        temp.chmod(0o600)
    temp.replace(path)


def register_workspace(codex_home, workspace):
    """Select this workspace and offer it to later chats. Written before any plugin is
    enabled, so a failure partway never leaves a plugin pointing at another workspace."""
    codex_home.mkdir(parents=True, exist_ok=True)
    write_json(codex_home / "accounting-workspace.json", {"workspace": str(workspace)}, private=True)
    if (workspace / "db/accounting.db").exists():
        workspace_instructions.ensure(workspace)
    registry = codex_home / "accounting-workspaces.json"
    known = json.loads(registry.read_text()) if registry.exists() else {"workspaces": []}
    if str(workspace) not in known["workspaces"]:
        known["workspaces"].append(str(workspace))
        write_json(registry, known)


def install_plugins(codex, codex_home, plugins):
    environment = dict(os.environ, CODEX_HOME=str(codex_home))

    def run_codex(*arguments):
        result = subprocess.run([codex, "plugin", *arguments, "--json"], env=environment,
                                check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    run_codex("marketplace", "add", str(ROOT))
    for name in plugins:
        location = Path(run_codex("add", f"{name}@{MARKETPLACE}")["installedPath"])
        skills = list((location / "skills").glob("*/SKILL.md"))
        if len(skills) != 1:
            raise RuntimeError(f"{name}: expected one installed skill, found {len(skills)}")
    discovered = run_codex("list", "--marketplace", MARKETPLACE)
    enabled = {i["name"] for i in discovered["installed"] if i.get("installed") and i.get("enabled")}
    missing = set(plugins) - enabled
    if missing:
        raise RuntimeError(f"Plugins not enabled after installation: {sorted(missing)}")


def local_server_choice(choice, codex_home):
    """Apply the user's answer. Never turn the setting on without a yes."""
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
    args = parse_args()
    plugins = plugin_names(args.local_only)
    config = args.codex_home / "config.toml"
    updated = planned_config(config, plugins)  # Validate before changing anything.
    # Synchronize bundled runtime and shared UI styles before npm compiles the email UI.
    subprocess.run([sys.executable, str(ROOT / "scripts/build_release.py")], check=True)
    if args.dependencies:
        install_dependencies(args.codex_home, args.local_only)
    if args.profile:
        subprocess.run([sys.executable, str(ROOT / "accounting_core/accounting_store.py"),
                        "--db", str(args.workspace / "db/accounting.db"),
                        "setup-accounting", "--request", str(args.profile)], check=True)
    register_workspace(args.codex_home, args.workspace)
    if args.register_only:
        temp = config.with_suffix(".accounting.tmp")
        temp.write_text(updated)
        temp.replace(config)
    else:
        install_plugins(args.codex, args.codex_home, plugins)
    buttons = local_server_choice(args.local_server, args.codex_home)
    desktop = None
    if args.desktop_app and not args.register_only:
        import launcher
        os.environ["CODEX_HOME"] = str(args.codex_home)
        launcher.install_window_package()
        desktop = str(launcher.build(args.desktop_app))
    if args.register_only:
        next_step = "Configuration written only; rerun without --register-only to install."
    else:
        next_step = ("Quit and reopen Codex. " if buttons.get("restart_codex") else "") \
            + "Open a new Codex chat. Ask: prepare my accounting period."
    print(json.dumps({
        "local_server": buttons["on"],
        "registered_plugins" if args.register_only else "installed_plugins": plugins,
        "workspace": str(args.workspace),
        **({"desktop_app": desktop} if desktop else {}),
        "next": next_step,
    }, indent=2))


if __name__ == "__main__":
    main()
