#!/bin/sh
# Start the inline BAS view server with Python 3.11+. GUI-started hosts get a bare PATH,
# so look in the usual install places, not only on PATH. Prefer a Python that can import
# openpyxl (installed or in the private accounting-python folder): the BAS workbook needs it.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPTS="$DIR/skills/manage-accounting/scripts"
ok() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; }
full() { "$1" -c "import sys; sys.path.insert(0, sys.argv[1]); import check_environment; check_environment.activate(); import openpyxl" "$SCRIPTS" 2>/dev/null; }
candidates() {
  for c in python3.13 python3.12 python3.11 python3; do command -v "$c" 2>/dev/null; done
  for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/3.1*/bin/python3 \
           "$HOME"/.pyenv/versions/3.1*/bin/python3 "$HOME"/.local/bin/python3; do
    [ -x "$p" ] && echo "$p"
  done
}
fallback=""
for p in $(candidates); do
  ok "$p" || continue
  full "$p" && exec "$p" "$SCRIPTS/bas_mcp.py" "$@"
  [ -n "$fallback" ] || fallback="$p"
done
# No Python with openpyxl: the view still works, only the workbook is not rewritten.
[ -n "$fallback" ] && exec "$fallback" "$SCRIPTS/bas_mcp.py" "$@"
echo "bas: Python 3.11 or newer is needed" >&2
exit 127
