# MCP server

Exposes `search_bills(category, date_from, date_to, candidates)` and the checklist UI resource. It consolidates host-supplied Gmail metadata; saving belongs to a separate plugin.

Build: `npm ci && npm run typecheck && npm run build`.
Run stdio: `./launch.sh --stdio` after building.

Optional HTTP development mode: `npm run serve`. `HOST` defaults to `127.0.0.1`, `PORT` to `3001`. Set `MCP_AUTH_TOKEN` in the process environment, or a generated token is stored at `~/.bill-search-app/mcp-token.txt`. The token is printed at startup; do not share those logs. Use an Authorization Bearer header. The example `.env` file is documentation; environment variables must be supplied by your shell or host.

`BILLS_ROOT_DEFAULT` sets the save folder suggested in the UI, not a local save operation. Personal-vendor settings live at `../data/personal-vendors.json`; see the root README.
