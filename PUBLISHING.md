# Publish ai-accounting

Create an empty GitHub repository named `ai-accounting` under your account. Review its visibility and the local files, then run these commands from this repository root:

```sh
git add .
git commit -m "Add Search Bills and Save Bills plugins"
git remote add origin https://github.com/YOUR_ACCOUNT/ai-accounting.git
git push -u origin main
```

Replace `YOUR_ACCOUNT` with your GitHub account. The repository uses MIT licensing. Enable private vulnerability reporting if available.

For releases, build each plugin first and package its folder separately, including generated `mcp-server/dist` files and dependency license notices. Exclude personal settings, tokens, bills, `.env`, `.git`, and `node_modules`. The source repository ZIP requires users to install dependencies and build.

Both plugins passed local build/type checks before consolidation. Save Bills also passed its two unit tests and bundled MCP startup check; Search Bills passed its filter and bundled MCP checks. The combined workflow has not run on GitHub. See each plugin README for runtime limitations.
