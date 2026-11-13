#!/usr/bin/env python3
"""Build self-contained plugins from one canonical accounting runtime."""

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from check_mcp_package import validate


def build(root, output):
    # review-invoices ships the canonical browser-checklist styling, including
    # when installed individually. Never maintain a separate theme copy by hand.
    checklist_css = root / "ui/checklist.css"
    if checklist_css.is_file():
        destination = root / "plugins/review-invoices/skills/review-invoices/assets/checklist.css"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(checklist_css, destination)
    core = root / "accounting_core"
    modules = sorted(core.glob("*.py"))
    if not modules:
        raise ValueError("Canonical runtime missing")
    # Validate every plugin before changing bundles or creating archives.
    for plugin in (root / "plugins").iterdir():
        if plugin.is_dir():
            validate(plugin)
    entries = []
    for plugin in sorted((root / "plugins").iterdir()):
        if not plugin.is_dir():
            continue
        manifest = plugin / ".codex-plugin/plugin.json"
        if not manifest.exists():
            raise ValueError(f"Missing Codex manifest: {plugin.name}")
        metadata = json.loads(manifest.read_text())
        skills = list((plugin / "skills").glob("*/SKILL.md"))
        if len(skills) != 1:
            raise ValueError(f"Expected exactly one skill: {plugin.name}")
        if (plugin / "accounting-runtime.json").exists():
            dest = skills[0].parent / "scripts"
            dest.mkdir(exist_ok=True)
            for module in modules:
                shutil.copy2(module, dest / module.name)
            # The ATO library's extracted text ships with the code; originals stay in the repo.
            library = root / "ato-library/library.json"
            bundled = skills[0].parent / "ato-library"
            if library.is_file():
                bundled.mkdir(exist_ok=True)
                shutil.copy2(library, bundled / library.name)
            elif bundled.exists():
                shutil.rmtree(bundled)
            (plugin / "accounting-runtime.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "schema": 5,
                        "sha256": {
                            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in modules
                        },
                    },
                    indent=2,
                )
                + "\n"
            )
        category = metadata.get("interface", {}).get("category", "Productivity")
        # Codex's marketplace schema only recognizes ON_INSTALL/ON_USE; defer
        # auth for MCP plugins that need an external connection (e.g. Gmail).
        policy = {
            "installation": "INSTALLED_BY_DEFAULT",
            "authentication": "ON_USE" if "mcpServers" in metadata else "ON_INSTALL",
        }
        entries.append(
            {
                "name": metadata["name"],
                "category": category,
                "source": {"source": "local", "path": "./plugins/" + plugin.name},
                "policy": policy,
            }
        )
    marketplace = root / ".agents/plugins/marketplace.json"
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    marketplace.write_text(
        json.dumps(
            {
                "name": "ai-accounting",
                "interface": {"displayName": "AI Accounting"},
                "plugins": entries,
            },
            indent=2,
        )
        + "\n"
    )
    if output:
        output.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            output / "ai-accounting.zip", "w", zipfile.ZIP_DEFLATED
        ) as archive:
            allowed = {
                "plugins",
                "accounting_core",
                "scripts",
                ".agents",
                "docs",
                "tests",
                "ui",
                "ato-library",
            }
            for f in root.rglob("*"):
                rel = f.relative_to(root)
                if not f.is_file() or f.is_symlink():
                    continue
                if any(
                    part in (".git", "node_modules", "__pycache__")
                    for part in rel.parts
                ):
                    continue
                if f.suffix in (
                    ".db",
                    ".pdf",
                    ".log",
                    ".pyc",
                    ".zip",
                    ".plugin",
                ) or f.name.startswith(".env"):
                    continue
                if rel.parts[0] in allowed or f.name in (
                    "README.md",
                    "LICENSE",
                    "VERSION",
                    "requirements.txt",
                ):
                    archive.write(f, rel)
        checksums = {
            f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in output.glob("*.zip")
        }
        (output / "SHA256SUMS.json").write_text(json.dumps(checksums, indent=2) + "\n")
    return {"plugins": len(entries), "runtime_modules": len(modules)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.output)))
