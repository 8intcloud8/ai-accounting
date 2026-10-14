#!/usr/bin/env python3
"""Install the AI Accounting suite into Codex; configure a local workspace.

Requires Python 3.11+. With --dependencies, installs isolated Python packages and
builds Gmail plugins using an available Node/npm. No database server is needed.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
import venv
from pathlib import Path


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
    args = parser.parse_args()
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
            for name in ("search-bills", "save-bills"):
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
    subprocess.run([sys.executable, str(root / "scripts/build_release.py")], check=True)
    marketplace = json.loads((root / ".agents/plugins/marketplace.json").read_text())
    plugins = [
        e["name"]
        for e in marketplace["plugins"]
        if not (args.local_only and e["name"] in ("search-bills", "save-bills"))
    ]
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
    config.parent.mkdir(parents=True, exist_ok=True)
    temp = config.with_suffix(".accounting.tmp")
    temp.write_text(updated)
    temp.replace(config)
    # A host-specific selector alongside config; plugins resolve this before defaults.
    selector = args.codex_home / "accounting-workspace.json"
    selector.parent.mkdir(parents=True, exist_ok=True)
    selector.write_text(json.dumps({"workspace": str(workspace)}) + "\n")
    selector.chmod(0o600)
    print(
        json.dumps(
            {
                "installed_plugins": plugins,
                "workspace": str(workspace),
                "next": "Open a new Codex chat. Ask: prepare my accounting period.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
