#!/bin/sh
# Resolve node without depending on the caller's PATH.
# GUI-spawned hosts (Claude Desktop/Cowork) inherit a minimal PATH that omits
# /usr/local/bin and /opt/homebrew/bin, so a bare "node" command fails there
# with "Unable to reach". Probe PATH first, then the usual install locations.

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if command -v node >/dev/null 2>&1; then
  NODE=$(command -v node)
else
  for c in \
    /usr/local/bin/node \
    /opt/homebrew/bin/node \
    /usr/bin/node \
    "$HOME/.local/bin/node" \
    "$HOME/.volta/bin/node" \
    "$HOME/n/bin/node"
  do
    [ -x "$c" ] && NODE="$c" && break
  done
fi

# nvm keeps versions outside any fixed path; take the highest it has.
if [ -z "$NODE" ] && [ -d "$HOME/.nvm/versions/node" ]; then
  for c in $(ls -1 "$HOME/.nvm/versions/node" 2>/dev/null | sort -V -r); do
    [ -x "$HOME/.nvm/versions/node/$c/bin/node" ] && NODE="$HOME/.nvm/versions/node/$c/bin/node" && break
  done
fi

if [ -z "$NODE" ]; then
  echo "save-bills: no node runtime found (checked PATH, /usr/local/bin, /opt/homebrew/bin, /usr/bin, volta, nvm)" >&2
  exit 127
fi

exec "$NODE" "$DIR/dist/server.mjs" "$@"
