# Xero MCP setup

Local Xero OAuth setup for Codex or another MCP host. Python 3 required; local server also needs Node.js/npm. No financial records are changed by setup.

Run `python3 scripts/oauth-setup.py` locally. New apps should use Xero's Auth Code with PKCE grant type and redirect URI `http://localhost:8000/callback`. Existing confidential Web Apps can use `--web-app`, with hidden local secret input. Default permissions are read-only accounting.

Credentials live in `~/.xero_mcp/state.json`, atomically saved under a rotation lock. Unix permissions: directory 0700, files 0600. Files are plaintext, not keychain storage. Windows requires private profile ACLs. Previous config/token files remain available for migration.

Register an MCP command in your host: Python 3, arguments `/absolute/path/scripts/xero_auth.py serve`. Registration is separate from OAuth and is not supplied automatically by this plugin. The compatibility shell/Node/PowerShell wrappers call the same Python implementation.

The launcher installs the official server pinned at version 0.0.17 into `~/.xero_mcp/runtime`. A local adapter supplies automatically refreshed tokens to the running server without modifying the official package. Refresh normally occurs at 28 minutes, two minutes before expiry, and is also checked on authentication after sleep. Concurrent calls share one refresh. Temporary failures retry after ten seconds; expired tokens are blocked. Financial operations are never replayed automatically.

No periodic reconnect is required. Reauthorization is needed if the refresh grant is revoked or expires. Confirm the intended organisation with a read-only call before financial work.

See [skill instructions](skills/setup-xero-mcp/SKILL.md) for setup, storage, scopes and troubleshooting.
