# Search Bills

A local MCP App and assistant skill for collecting Gmail bill candidates into an interactive checklist. The assistant searches connected Gmail accounts; this server receives metadata and does not connect to Gmail itself.

## Requirements

- Node.js 22 or newer and npm.
- macOS or Linux for the bundled shell launcher.
- An MCP-capable assistant with a connected Gmail search tool.
- MCP Apps support for the embedded checklist. Other hosts receive structured results; interactive fallback depends on host tools.
- The separate **save-bills** plugin is required to download selections. This repository contains no saving or Xero integration.

## Install from source

Clone or download ai-accounting, then run from `plugins/search-bills/`:

```sh
cd mcp-server
npm ci
npm run typecheck
npm run build
cd ..
cp data/personal-vendors.example.json data/personal-vendors.json
```

For a Claude-compatible plugin host, load this folder using its local-plugin installation flow. The root `.mcp.json` uses that host's `CLAUDE_PLUGIN_ROOT` expansion.

For other MCP hosts, register the following server, replacing the path with your clone's absolute path, and make `skills/search-bills/SKILL.md` available to the assistant:

```json
{
  "mcpServers": {
    "bill-search-app": {
      "command": "/bin/sh",
      "args": ["/absolute/path/to/search-bills/mcp-server/launch.sh", "--stdio"]
    }
  }
}
```

On Windows, launch `node` directly with the absolute path to `mcp-server/dist/server.mjs` followed by `--stdio`. Host plugin installation and app rendering vary; universal one-click installation is not claimed.

## Use

Ask: “Find business bills from my connected Gmail accounts for 1 July to 30 September 2026.” Supply category and dates when missing. The checklist shows the completed search's category and dates as a read only summary; ask in chat to run a different search. Review candidates and configured exclusions before saving. Selecting Save sends a request back to the assistant; it requires the separate saving plugin.

## Personal-vendor filter

Fresh installations have **no exclusions**. Edit `data/personal-vendors.json`:

```json
{
  "personalVendors": ["personal-supplier.example"],
  "suppressed": []
}
```

Business searches exclude case-insensitive substrings found in sender names or email addresses. Personal and unlabelled searches do not apply the filter. Keep patterns specific to avoid false matches. `suppressed` disables matching entries from `mcp-server/vendors.config.json`.

Settings remain inside the plugin, are reread on every search, and are ignored by Git. Back up this file before replacing or reinstalling the plugin. Never publish your own rules, inbox exports, or bill documents.

## Privacy and limitations

- Candidate sender, subject, date, and attachment filenames pass through the assistant and local MCP server. Review your host and Gmail connector's data policies.
- The server does not determine whether an expense is deductible or eligible for GST credits.
- The host must scope Gmail queries to the requested date range; the consolidator does not independently reject out-of-range candidates.
- Deduplication uses thread IDs. Gmail links target account slot 0; check the correct account when using multiple accounts.
- Only `search_bills` is exposed. Vendor settings are edited locally.
- Default operation uses stdio. Optional HTTP mode uses a token and binds to loopback; see `mcp-server/README.md`.

## Development and releases

```sh
cd mcp-server
npm ci
npm run typecheck
npm run build
```

CI builds on macOS and Linux. Source control excludes dependencies, generated bundles, and personal settings. Build before creating an installable ZIP; include `mcp-server/dist`, manifests, source, skill, and the example settings. Exclude `node_modules`, `.git`, `.env`, and `data/personal-vendors.json`.

See CONTRIBUTING.md and SECURITY.md. Licensed under the [MIT License](LICENSE). Third-party dependencies retain their respective licenses.
