#!/bin/sh
# One-step install of AI Accounting into Codex on a Mac.
# Usage (paste into Terminal):
#   curl -fsSL https://raw.githubusercontent.com/8intcloud8/ai-accounting/main/scripts/install.sh | sh
set -e

REPO="8intcloud8/ai-accounting"
MARKETPLACE="ai-accounting"

codex=""
for candidate in "$(command -v codex 2>/dev/null)" \
    /Applications/Codex.app/Contents/Resources/codex \
    /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex \
    "$HOME/Applications/Codex.app/Contents/Resources/codex" \
    "$HOME/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then codex="$candidate"; break; fi
done
if [ -z "$codex" ]; then
  echo "Codex was not found. Install the Codex app (or ChatGPT with Codex) first, open it once, then run this again."
  exit 1
fi

# Codex downloads the plugins with git, which comes with Apple's free developer tools.
if ! xcode-select -p >/dev/null 2>&1 && ! command -v git >/dev/null 2>&1; then
  echo "First, Apple's developer tools are needed (free, about 5 minutes)."
  echo "A window will open: click Install and wait for it to finish, then run this command again."
  xcode-select --install >/dev/null 2>&1 || true
  exit 1
fi

echo "Adding AI Accounting to Codex..."
"$codex" plugin marketplace add "$REPO" >/dev/null 2>&1 || "$codex" plugin marketplace upgrade "$MARKETPLACE" >/dev/null

echo "Installing the accounting plugins..."
"$codex" plugin list 2>/dev/null | awk -v m="@$MARKETPLACE" 'index($1, m) {print $1}' | while read -r plugin; do
  "$codex" plugin add "$plugin" >/dev/null && echo "  installed ${plugin%@*}"
done

python_ok=""
for py in python3.13 python3.12 python3.11 python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    python_ok=1; break
  fi
done

echo
if [ -z "$python_ok" ]; then
  echo "One more thing: install Python (free) from https://www.python.org/downloads/"
  echo "Download the macOS installer, open it and click through."
  echo
fi
echo "Done. Quit Codex completely and open it again."
echo "Then start a new chat and type: Set up my accounting"
