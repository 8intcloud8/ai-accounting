#!/bin/sh
# Start the inline BAS view server with Python 3.11+. GUI-started hosts get a bare PATH,
# so look in the usual install places, not only on PATH.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ok() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; }
for c in python3.13 python3.12 python3.11 python3; do
  p=$(command -v "$c" 2>/dev/null) && ok "$p" && exec "$p" "$DIR/skills/manage-accounting/scripts/bas_mcp.py" "$@"
done
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/3.1*/bin/python3 \
         "$HOME"/.pyenv/versions/3.1*/bin/python3 "$HOME"/.local/bin/python3; do
  [ -x "$p" ] && ok "$p" && exec "$p" "$DIR/skills/manage-accounting/scripts/bas_mcp.py" "$@"
done
echo "bas: Python 3.11 or newer is needed" >&2
exit 127
