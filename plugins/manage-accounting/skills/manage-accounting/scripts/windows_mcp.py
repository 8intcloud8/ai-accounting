"""Start the plugin MCP servers on Windows, where the plugins' /bin/sh launchers cannot run.

Plugins declare their servers with `/bin/sh` (it finds Python/Node from a GUI app's bare
PATH on a Mac). Windows has no /bin/sh, and a plugin cannot declare a per-OS command.
So on Windows, setup turns each plugin server off in the Codex config and registers the
same server name with this file as the launcher, run by the Python that ran setup.

The launcher is copied to a fixed folder in the Codex home, and finds the newest
installed plugin version every time it starts, so plugin updates need no new setup.
Only standard library: it must start before any package is installed.
"""

import json
import os
import re
import runpy
import shutil
import subprocess
import sys

MARKETPLACE = "ai-accounting"
# server name -> (plugin, how it runs)
SERVERS = {
    "bas": ("manage-accounting", "python"),
    "bill-search-app": ("search-email-invoices", "node"),
    "save-invoices": ("save-invoices", "node"),
}
FOLDER = "accounting-mcp"


def codex_home():
    return os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")


def newest(plugin, home=None):
    """The highest installed version folder of `plugin`, or None."""
    root = os.path.join(home or codex_home(), "plugins", "cache", MARKETPLACE, plugin)
    try:
        names = os.listdir(root)
    except OSError:
        return None

    def key(name):
        return tuple(int(n) for n in re.findall(r"\d+", name))

    names = [n for n in names if os.path.isdir(os.path.join(root, n))]
    return os.path.join(root, max(names, key=key)) if names else None


def fail(text):
    sys.stderr.write("accounting MCP: " + text + "\n")
    sys.exit(127)


def run_python(folder):
    scripts = os.path.join(folder, "skills", "manage-accounting", "scripts")
    sys.path.insert(0, scripts)
    import check_environment  # the copy bundled with the plugin
    check_environment.activate()
    sys.argv = [os.path.join(scripts, "bas_mcp.py")] + sys.argv[3:]
    runpy.run_path(sys.argv[0], run_name="__main__")


def run_node(server, folder):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import check_environment
    node = check_environment.find_node()
    if not node:
        fail(server + ": Node.js is not installed (https://nodejs.org/)")
    code = os.path.join(folder, "mcp-server")
    entry = os.path.join(code, "dist", "server.mjs")
    if not os.path.isfile(entry):  # A marketplace install ships source only: build once.
        npm = shutil.which("npm") or os.path.join(os.path.dirname(node), "npm.cmd")
        for step in (["ci", "--no-audit", "--no-fund"], ["run", "build"]):
            if subprocess.run([npm] + step, cwd=code, stdout=sys.stderr).returncode:
                fail(server + ": first-run build failed (npm " + step[0] + ")")
    # Same as the plugins' launch.sh: stdio transport, not the HTTP port.
    sys.exit(subprocess.run([node, entry, "--stdio"] + sys.argv[3:]).returncode)


def launch(server):
    if server not in SERVERS:
        fail("unknown server " + server)
    plugin, kind = SERVERS[server]
    folder = newest(plugin)
    if not folder:
        fail(plugin + " is not installed")
    run_python(folder) if kind == "python" else run_node(server, folder)


def toml_string(text):
    return json.dumps(text)  # A JSON string is a valid TOML basic string.


def planned_config(text, python, launcher):
    """`text` with the Windows server entries added; existing entries are kept."""
    import tomllib
    existing = tomllib.loads(text)
    added = []
    for server, (plugin, _) in SERVERS.items():
        if server not in existing.get("mcp_servers", {}):
            added.append("[mcp_servers.%s]\ncommand = %s\nargs = [%s, \"launch\", %s]\n" % (
                toml_string(server), toml_string(python), toml_string(launcher), toml_string(server)))
        key = plugin + "@" + MARKETPLACE
        if "enabled" not in existing.get("plugins", {}).get(key, {}).get("mcp_servers", {}).get(server, {}):
            added.append("[plugins.%s.mcp_servers.%s]\nenabled = false\n" % (
                toml_string(key), toml_string(server)))
    if not added:
        return text
    updated = text.rstrip("\n") + ("\n\n" if text.strip() else "") + "\n".join(added)
    tomllib.loads(updated)
    return updated


def status(home=None):
    """True when the Windows server entries are in the Codex config."""
    path = os.path.join(home or codex_home(), "config.toml")
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    return planned_config(text, sys.executable, "") == text


def apply(home=None):
    """Copy the launcher to a fixed folder and register the servers. Returns True when
    the config changed (Codex must be restarted to pick it up)."""
    home = home or codex_home()
    folder = os.path.join(home, FOLDER)
    os.makedirs(folder, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("windows_mcp.py", "check_environment.py"):
        shutil.copyfile(os.path.join(here, name), os.path.join(folder, name))
    path = os.path.join(home, "config.toml")
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        text = ""
    updated = planned_config(text, sys.executable, os.path.join(folder, "windows_mcp.py"))
    if updated == text:
        return False
    temp = path + ".accounting.tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(updated)
    os.replace(temp, path)
    return True


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "launch":
        launch(sys.argv[2])
    elif sys.argv[1:] == ["apply"]:
        print(json.dumps({"changed": apply(), "restart_codex": True}))
    else:
        fail("usage: windows_mcp.py launch <server> | apply")
