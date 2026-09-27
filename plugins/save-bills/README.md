# Save Bills

A local MCP plugin that saves selected Gmail bill attachments and inline receipts. Exposes one tool: `save_bills`. The companion search-bills plugin discovers candidates; this plugin saves only the selections supplied by the assistant.

## Requirements

- Node.js 22.12 or newer and npm.
- An MCP host with a Gmail connector that returns temporary `file_uri.download_url` links.
- macOS or Linux for the supplied shell launcher. On Windows, register `node` directly with the absolute path to `mcp-server/dist/server.mjs` and `--stdio`.
- Chrome/Puppeteer for inline email-to-PDF conversion. Attachment downloads do not require Chrome.

No separate Gmail OAuth client is used by this plugin. Download links currently must be HTTPS URLs at a single subdomain of `oaiusercontent.com`, with a `/files/` path. Connectors returning different URL formats are unsupported.

## Build and install

Clone or extract ai-accounting. From `plugins/save-bills/`:

```sh
cd mcp-server
npm ci
npm run typecheck
npm test
npm run build
cd ..
```

Puppeteer may download a browser during installation. To use an existing browser, set `PUPPETEER_SKIP_DOWNLOAD=true` while installing and supply its absolute executable path through `PUPPETEER_EXECUTABLE_PATH` when running. On macOS the renderer also checks the standard Google Chrome application path.

Load the built folder through your host's local plugin flow. Codex metadata is in `.codex-plugin/plugin.json`; `.mcp.json` uses a plugin-relative working directory. For Claude and other MCP hosts, use manual server registration:

```json
{
  "mcpServers": {
    "save-bills": {
      "command": "/bin/sh",
      "args": ["/absolute/path/to/save-bills/mcp-server/launch.sh", "--stdio"]
    }
  }
}
```

Make `skills/save-bills/SKILL.md` available to your assistant. The Codex relative-cwd setting follows the [Codex MCP configuration implementation](https://github.com/openai/codex/blob/main/codex-rs/codex-mcp/src/plugin_config.rs).

## Use

Select bills in your search checklist, then ask the assistant to save those selections. It retrieves exact attachment links or inline bodies and calls `save_bills` in batches of up to five threads. Keep links and email bodies within tool orchestration, not chat output. Retry failed items with fresh links.

Saved files go under `<root_folder>/<category>/<date_range>/`, with `manifest.csv` appended after each run. The tool requires a `root_folder` string; an empty string uses `BILLS_ROOT_DEFAULT` or `~/Documents/Bills`. Categories are personal, business, or bills. `date_range` has the form `YYYY-MM-DD_YYYY-MM-DD`.

The tool streams attachments, checks nonempty writes, retries once, and chooses unused filenames. It does not determine tax eligibility, verify invoice authenticity, or upload to Xero. Avoid concurrent calls to the same destination folder. Re-saving the same selection creates additional files; it is not transaction deduplication.

## Configuration

Set variables in your shell or MCP host; `.env.example` is documentation and is not automatically loaded.

| Variable | Purpose |
|---|---|
| `BILLS_ROOT_DEFAULT` | Default save folder when the supplied root is empty |
| `SAVE_CONCURRENCY` | Positive number of concurrent items; default 5 |
| `PUPPETEER_EXECUTABLE_PATH` | Optional browser executable for inline PDF rendering |
| `HOST`, `PORT` | Optional HTTP mode; defaults 127.0.0.1:3001 |
| `MCP_AUTH_TOKEN` | Optional HTTP bearer token |
| `MCP_AUTH_TOKEN_PATH` | Optional generated-token file path |

Prefer stdio. HTTP development mode (`npm run serve`) prints its token and defaults to storing it at `~/.bill-search-app/mcp-token.txt`. Do not share those logs or expose the service publicly without additional review.

## Privacy and limits

Bill documents and the manifest contain private financial information. Store them outside the repository. Git ignores common bill, token, environment, and output files; inspect changes before publishing.

Attachments are limited to 100 MB each and redirects are rejected. Inline HTML renders with JavaScript disabled, but external images and styles may still load and contact remote servers. Do not treat PDF conversion as an offline sandbox. Gmail manifest links target account slot 0; check the correct account when using multiple inboxes.

## Development

Run `npm run typecheck`, `npm test`, and `npm run build` inside `mcp-server`. CI covers macOS and Linux. Unit tests use synthetic metadata and mocked downloads; they do not access Gmail. Browser installation and inline PDF conversion are separate from those tests.

See CONTRIBUTING.md, SECURITY.md, and the repository root PUBLISHING.md. Licensed under the [MIT License](LICENSE). Dependencies retain their own licenses.
