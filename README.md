# AI Accounting

Accounting assistant skills and local MCP plugins, licensed under MIT.

## Plugins

| Plugin | Purpose |
|---|---|
| [Search Bills](plugins/search-bills/README.md) | Find Gmail bill candidates and show a checklist, with configurable personal-vendor exclusions. |
| [Save Bills](plugins/save-bills/README.md) | Save selected attachments and inline receipts locally, with a CSV manifest. |

Each plugin is independently built and installed. Gmail access comes from your assistant's connected Gmail tools. No Xero integration is included.

## Setup

Clone or download this repository. Follow each plugin's README for requirements, build commands, and host registration. Use the plugin folder under `plugins/` as its installation root; the repository root is not an installable plugin.

```sh
cd plugins/search-bills/mcp-server
npm ci
npm run typecheck
npm run build
```

Repeat in `plugins/save-bills/mcp-server`, also running `npm test`. Save Bills requires Chrome/Puppeteer for inline PDF conversion. See its README for browser setup.

## Structure

```text
ai-accounting/
  plugins/
    search-bills/
      skills/search-bills/SKILL.md
      mcp-server/
    save-bills/
      skills/save-bills/SKILL.md
      mcp-server/
  .github/workflows/ci.yml
  LICENSE
```

## Adding future plugins

Create `plugins/<plugin-name>/` with its skill instructions, host manifest, README, and any server code. Keep each plugin self-contained. Add it to the table above and extend the root CI workflow with its build and test steps. Standalone skills can live in a plugin's `skills/` directory without requiring an MCP server.

Do not commit invoices, email exports, personal vendor settings, credentials, or temporary download links. Review each plugin's documented limitations before use.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [PUBLISHING.md](PUBLISHING.md).

## License

[MIT](LICENSE), copyright 2026 Ammar. Dependencies retain their own licenses.
