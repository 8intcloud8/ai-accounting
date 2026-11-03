---
name: setup-xero-mcp
description: Configure or repair a local Xero OAuth connection and MCP launcher. Use for Xero authentication errors or initial Xero MCP setup.
metadata:
  version: "0.10.0"
---

Use the bundled scripts on the user's desktop computer. Resolve `../../scripts/` relative to this skill directory. Do not collect client secrets, passwords, authorization codes or tokens in chat, launchers, command arguments or reports.

## Setup

1. Check Python 3 and, for the local MCP server, Node.js/npm (`npx`). Check the host's existing Xero tools first: an existing connector is separate from this plugin and may already work. Do not overwrite it.
2. For a new developer app use Xero's **Auth Code with PKCE** grant type, with redirect URI exactly `http://localhost:8000/callback`. PKCE needs a Client ID and no client secret. For an existing Web App, use the legacy `--web-app` option; the script asks for its secret locally with hidden input. Never distribute a shared client secret.
3. Launch `python3 <plugin>/scripts/oauth-setup.py` in a visible local terminal (Windows: `py -3`). User enters Client ID there and approves Xero access in their browser. For an existing Web App append `--web-app`. A double-click launcher may invoke this script by absolute path but must not embed credentials. Keep the complete scripts directory together.
4. Default scopes are read-only accounting plus `offline_access`. Explain these permissions. If the user needs writes, choose only the required scopes from current Xero documentation and pass `--scopes "... offline_access"` during reauthorization. Allocation of scopes does not authorize financial writes.
5. Script validates random callback state and PKCE, limits the wait to five minutes, saves credentials and the rotating refresh token atomically, then lists connected organisations. Identify the intended organisation explicitly when more than one exists. Do not claim an organisation is connected unless the connections query succeeds.

## Local storage

`~/.xero_mcp/state.json` stores the Client ID, refresh token and, for legacy Web Apps, the client secret. Unix directory/file permissions are 0700/0600. This is local plaintext protected by filesystem permissions, not encryption or an OS keychain. On Windows use a private user profile with restricted ACLs; POSIX permission bits do not enforce Windows ACLs. Do not copy storage into the checkout, cloud folders or chat.

Existing `~/.xero_mcp/config` and `refresh_token` files are read as data for migration on first refresh. They are retained; never delete existing credentials automatically. Fresh PKCE authorization replaces only the new state file. Authentication/refresh holds an OS lock to prevent simultaneous token rotation.

## Register and verify MCP

This plugin supplies a skill and scripts, **not automatic MCP registration**. Configure the intended host to launch Python 3 with absolute arguments `<plugin>/scripts/xero_auth.py serve`. Use the host's native MCP configuration workflow; inspect current configuration before editing it. No secrets belong in the MCP configuration. Restart or reconnect the configured host server, then perform a read-only organisation or connection lookup. Report setup, registration and verified API access separately.

The launcher installs the pinned official `@xeroapi/xero-mcp-server@0.0.17` runtime under `~/.xero_mcp/runtime` on first use. It attaches a local token manager to that server's authentication interface without modifying upstream package files. Node.js/npm and network access are required for this first installation. Other upstream versions must be reviewed before changing the pin.

Access tokens refresh automatically two minutes before their reported expiry (normally at 28 minutes). The manager updates the running SDK token set, and authentication requests check freshness too, including after laptop sleep. Concurrent requests share one refresh; Python serializes rotation across processes and saves the replacement refresh token atomically. No routine reconnect or repeated login is needed while refresh authorization remains valid.

Transient refresh failures retry after ten seconds; a still-valid token remains available. Expired tokens are blocked until refresh succeeds. Persistent authorization failures require reauthorization. The adapter never retries a financial API operation or restarts the server to refresh tokens.

## Failures

- Port 8000 occupied: stop setup, identify the process; do not kill it automatically.
- Consent declined, wrong state/path, timeout: no token exchange or overwrite.
- Token request failure: existing file remains intact. Do not print raw token responses. Retry a failed refresh promptly; Xero allows a 30-minute recovery grace period for the previous token. If recovery fails, reauthorize.
- Unused refresh tokens expire after 60 days. OAuth success alone does not prove MCP registration, scopes for every tool, or correct organisation selection.

Official references: [PKCE](https://developer.xero.com/documentation/guides/oauth2/pkce-flow/), [token handling](https://developer.xero.com/documentation/guides/oauth2/token-types/), [scopes](https://developer.xero.com/documentation/guides/oauth2/scopes/), [official MCP server](https://github.com/XeroAPI/xero-mcp-server).
