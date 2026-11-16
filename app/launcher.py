#!/usr/bin/env python3
"""Make the double-clickable "BAS" app on a Mac, and install its window package.

The app is a tiny bundle that runs app/bas_app.py from this checkout with this
Python. Its window needs pywebview, installed into the same private folder the
setup check uses, so nothing else on the computer changes. Without it the app
opens in the default browser instead.
"""

import argparse
import json
import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "accounting_core"))
import check_environment  # noqa: E402

WINDOW_PACKAGE = "pywebview>=5,<7"
LOG = "~/Library/Logs/BAS.log"
SCRIPT = """#!/bin/sh
# Opens the BAS app. Messages go to the log; a failed start shows an alert.
LOG="$HOME/Library/Logs/BAS.log"
mkdir -p "$HOME/Library/Logs"
{python} {app} "$@" >>"$LOG" 2>&1 || /usr/bin/osascript -e \
  'display alert "BAS could not start" message "Details are in ~/Library/Logs/BAS.log"'
"""


def build(dest, python=sys.executable, app=HERE / "bas_app.py"):
    """Write BAS.app into `dest` and return its path. Rebuilding replaces it."""
    bundle = Path(dest).expanduser() / "BAS.app"
    macos = bundle / "Contents/MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    executable = macos / "BAS"
    executable.write_text(SCRIPT.format(python=shlex.quote(str(python)), app=shlex.quote(str(app))))
    executable.chmod(0o755)
    with open(bundle / "Contents/Info.plist", "wb") as handle:
        plistlib.dump({
            "CFBundleName": "BAS", "CFBundleDisplayName": "BAS", "CFBundleExecutable": "BAS",
            "CFBundleIdentifier": "local.ai-accounting.bas", "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "1.0", "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
        }, handle)
    return bundle


def has_window_package():
    return check_environment.has_package("webview")


def install_window_package():
    """pip-install pywebview into the private folder. Returns True when importable."""
    if has_window_package():
        return True
    folder = check_environment.private_folder()
    python = os.path.join(folder, "bin", "python")
    if not os.path.exists(python):
        subprocess.run([sys.executable, "-m", "venv", folder], check=True)
    subprocess.run([python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    WINDOW_PACKAGE], check=True)
    return has_window_package()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path.home() / "Applications")
    parser.add_argument("--no-packages", action="store_true", help="Skip installing pywebview")
    args = parser.parse_args()
    window = has_window_package() if args.no_packages else install_window_package()
    bundle = build(args.dest)
    print(json.dumps({"app": str(bundle), "own_window": window, "log": LOG}, indent=2))


if __name__ == "__main__":
    main()
