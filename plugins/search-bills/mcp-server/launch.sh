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

# npm (and node_modules/.bin tools it runs, e.g. vite/esbuild) are
# "#!/usr/bin/env node" scripts: running them by absolute path still makes
# the OS resolve "node" through PATH. A minimal GUI PATH can satisfy our own
# probing above yet still lack node's directory, so npm fails with
# "env: node: No such file or directory" even though $NODE is valid. Fix
# that for every child process below, not just npm's shebang.
PATH="$(dirname "$NODE")${PATH:+:$PATH}"
export PATH

# Killing just the subshell below leaves its "npm ci"/"npm run build" child
# (and that child's own esbuild/vite workers) running orphaned, free to race
# a subsequent retry's npm ci against the same node_modules. Sweep two
# levels of descendants too; degrades gracefully if pgrep is unavailable.
kill_build_tree() {
  if command -v pgrep >/dev/null 2>&1; then
    for child in $(pgrep -P "$1" 2>/dev/null); do
      for grandchild in $(pgrep -P "$child" 2>/dev/null); do
        kill "$grandchild" 2>/dev/null
      done
      kill "$child" 2>/dev/null
    done
  fi
  kill "$1" 2>/dev/null
}

# A marketplace/git install has no prebuilt dist/ (gitignored); build it on
# first launch. A release ZIP ships dist/ already, so this is a no-op there.
if [ ! -f "$DIR/dist/server.mjs" ]; then
  LOCK="$DIR/.build.lock"
  PIDFILE="$LOCK/pid"
  attempt=0
  while [ ! -f "$DIR/dist/server.mjs" ]; do
    if mkdir "$LOCK" 2>/dev/null; then
      echo $$ >"$PIDFILE" 2>/dev/null
      # A trap only overrides the default terminate-on-signal behavior; it
      # does not exit by itself, so without an explicit exit here a signal
      # would just clean up the lock and then let the build run to
      # completion anyway. Exit so an interrupted launch actually stops.
      trap 'rm -f "$PIDFILE" 2>/dev/null; rmdir "$LOCK" 2>/dev/null; exit 1' INT TERM

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
        rm -f "$PIDFILE" 2>/dev/null
        rmdir "$LOCK" 2>/dev/null
        trap - INT TERM
        exit 127
      fi

      ( cd "$DIR" && "$NPM" ci --no-audit --no-fund && "$NPM" run build ) >&2 &
      BUILD_PID=$!
      trap 'kill_build_tree "$BUILD_PID"; rm -f "$PIDFILE" 2>/dev/null; rmdir "$LOCK" 2>/dev/null; exit 1' INT TERM
      wait "$BUILD_PID"
      BUILD_STATUS=$?
      rm -f "$PIDFILE" 2>/dev/null
      rmdir "$LOCK" 2>/dev/null
      trap - INT TERM
      if [ "$BUILD_STATUS" -ne 0 ]; then
        echo "bill-search-app: first-run build failed (npm ci/build exited $BUILD_STATUS)" >&2
        exit 1
      fi
      break
    fi

    # Another launch holds the lock. Reclaim it only if its owner process is
    # confirmably gone (killed build, crash, power loss) — never merely
    # because the lock is old, which would preempt a slow-but-alive build
    # and let two npm ci/build runs race the same node_modules/dist. If the
    # owner is alive (or we cannot yet tell — the pidfile write lands just
    # after mkdir), wait for it rather than racing it.
    owner_pid=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$owner_pid" ] && ! kill -0 "$owner_pid" 2>/dev/null; then
      rm -f "$PIDFILE" 2>/dev/null
      rmdir "$LOCK" 2>/dev/null
      continue
    fi

    attempt=$((attempt + 1))
    if [ "$attempt" -ge 180 ]; then
      # Give up without touching the lock: its owner is still alive for all
      # we can tell, so removing it here would be the exact race this lock
      # exists to prevent. The owner's own build, when it finishes, cleans
      # up its lock either way.
      break
    fi
    sleep 1
  done
  if [ ! -f "$DIR/dist/server.mjs" ]; then
    echo "bill-search-app: dist/server.mjs still missing after build attempt" >&2
    exit 1
  fi
fi

exec "$NODE" "$DIR/dist/server.mjs" "$@"
