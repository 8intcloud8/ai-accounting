#!/usr/bin/env python3
"""Check this computer can run the accounting plugins, and install what is missing.

Plugins added from the Codex plugin list arrive without the two Python packages
they need. `status` reports what is missing in plain words; `install` puts the
packages in a private folder in the Codex home, so nothing else on the computer
changes and plugin updates do not remove them.

Runs on old Pythons on purpose (no newer syntax), so it can say "Python is too
old" instead of crashing.
"""

import argparse
import glob
import importlib
import json
import os
import shutil
import site
import subprocess
import sys

MIN_PYTHON = (3, 11)
# Keep in step with requirements.txt.
PACKAGES = {"pdfplumber": "pdfplumber>=0.11,<0.12", "openpyxl": "openpyxl>=3.1,<4"}
USES = {"pdfplumber": "reading PDF bank statements", "openpyxl": "the Excel review file"}
NODE_PLACES = (
    "/usr/local/bin/node",
    "/opt/homebrew/bin/node",
    "/usr/bin/node",
    "~/.local/bin/node",
    "~/.volta/bin/node",
    "~/n/bin/node",
)
PYTHON_HELP = (
    "This computer's Python is too old (found {found}; 3.11 or newer is needed). "
    "Download and install Python from https://www.python.org/downloads/ , then start a new chat."
)
NODE_HELP = (
    "Node.js is not installed. Finding and saving invoices from email needs it; everything "
    "else works without it. Download the LTS installer from https://nodejs.org/ if you want "
    "the email features."
)


def codex_home():
    return os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")


def private_folder():
    """One folder per Python version: compiled packages do not mix across versions."""
    return os.path.join(codex_home(), "accounting-python", "py%d.%d" % sys.version_info[:2])


def activate():
    """Make privately installed packages importable. Safe to call when none exist."""
    for path in glob.glob(os.path.join(private_folder(), "lib", "python*", "site-packages")):
        if path not in sys.path:
            site.addsitedir(path)


def has_package(name):
    activate()
    importlib.invalidate_caches()
    try:
        importlib.import_module(name)
        return True
    except Exception:  # A broken install counts as missing.
        return False


def find_node():
    found = shutil.which("node")
    if found:
        return found
    for place in NODE_PLACES:
        place = os.path.expanduser(place)
        if os.access(place, os.X_OK):
            return place
    versions = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
    return versions[-1] if versions else None


def status():
    python_ok = sys.version_info[:2] >= MIN_PYTHON
    missing = [name for name in sorted(PACKAGES) if not has_package(name)] if python_ok else sorted(PACKAGES)
    node = find_node()
    messages = []
    if not python_ok:
        messages.append(PYTHON_HELP.format(found="%d.%d" % sys.version_info[:2]))
    elif missing:
        messages.append(
            ("A small helper package needs" if len(missing) == 1 else "Two small helper packages need")
            + " a one-off install (about a minute, needs internet): "
            + "; ".join("%s for %s" % (name, USES[name]) for name in missing) + "."
        )
    if not node:
        messages.append(NODE_HELP)
    return {
        "ready": python_ok and not missing,
        "python": sys.executable,
        "python_version": "%d.%d.%d" % sys.version_info[:3],
        "python_ok": python_ok,
        "missing_packages": missing,
        "can_install_packages": python_ok and bool(missing),
        "email_ready": bool(node),
        "node": node,
        "messages": messages,
    }


def install():
    """Install the missing packages into the private folder; return the new status."""
    before = status()
    if not before["python_ok"]:
        raise SystemExit(before["messages"][0])
    if not before["missing_packages"]:
        return before
    folder = private_folder()
    python = os.path.join(folder, "bin", "python")
    try:
        if not os.path.exists(python):
            subprocess.run([sys.executable, "-m", "venv", folder], check=True)
        subprocess.run(
            [python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
            + [PACKAGES[name] for name in before["missing_packages"]],
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as error:
        raise SystemExit(
            "Could not install the helper packages (%s). Check the internet connection and "
            "try again; if it was blocked, allow this one command to use the network and "
            "write to %s." % (error, folder)
        )
    after = status()
    if after["missing_packages"]:
        raise SystemExit("Installed, but still cannot load: " + ", ".join(after["missing_packages"]))
    return after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "install"))
    args = parser.parse_args()
    print(json.dumps(status() if args.action == "status" else install(), indent=2))


if __name__ == "__main__":
    main()
