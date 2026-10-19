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
  echo "bill-search-app: no node runtime found (checked PATH, /usr/local/bin, /opt/homebrew/bin, /usr/bin, volta, nvm)" >&2
  exit 127
fi

# A marketplace/git install has no prebuilt dist/ (gitignored); build it on
# first launch. A release ZIP ships dist/ already, so this is a no-op there.
if [ ! -f "$DIR/dist/server.mjs" ]; then
  LOCK="$DIR/.build.lock"
  if mkdir "$LOCK" 2>/dev/null; then
    if command -v npm >/dev/null 2>&1; then
      NPM=$(command -v npm)
    else
      for c in \
        /usr/local/bin/npm \
        /opt/homebrew/bin/npm \
        /usr/bin/npm \
        "$HOME/.local/bin/npm" \
        "$HOME/.volta/bin/npm" \
        "$HOME/n/bin/npm"
      do
        [ -x "$c" ] && NPM="$c" && break
      done
    fi
    if [ -z "$NPM" ] && [ -d "$HOME/.nvm/versions/node" ]; then
      for c in $(ls -1 "$HOME/.nvm/versions/node" 2>/dev/null | sort -V -r); do
        [ -x "$HOME/.nvm/versions/node/$c/bin/npm" ] && NPM="$HOME/.nvm/versions/node/$c/bin/npm" && break
      done
    fi
    if [ -z "$NPM" ]; then
      echo "bill-search-app: dist/server.mjs missing and no npm runtime found to build it" >&2
      rmdir "$LOCK" 2>/dev/null
      exit 127
    fi
    ( cd "$DIR" && "$NPM" ci --no-audit --no-fund && "$NPM" run build ) >&2
    BUILD_STATUS=$?
    rmdir "$LOCK" 2>/dev/null
    if [ "$BUILD_STATUS" -ne 0 ]; then
      echo "bill-search-app: first-run build failed (npm ci/build exited $BUILD_STATUS)" >&2
      exit 1
    fi
  else
    # Another launch is already building; wait for it rather than racing it.
    i=0
    while [ ! -f "$DIR/dist/server.mjs" ] && [ "$i" -lt 180 ]; do
      sleep 1
      i=$((i + 1))
    done
  fi
  if [ ! -f "$DIR/dist/server.mjs" ]; then
    echo "bill-search-app: dist/server.mjs still missing after build attempt" >&2
    exit 1
  fi
fi

exec "$NODE" "$DIR/dist/server.mjs" "$@"
