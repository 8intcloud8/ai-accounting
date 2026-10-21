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

## MCP launch regression gate

After building, create client archives with the checked packager (Python 3.11+):

```sh
python scripts/check_mcp_package.py plugins/save-bills --output dist/save-bills-1.0.1.zip --expected-tool save_bills
python scripts/check_mcp_package.py plugins/search-bills --output dist/search-bills.zip --expected-tool search_bills
```

The packager rejects unresolved variables, missing launchers and paths outside the
plugin. It extracts the ZIP into a temporary directory, starts the declared command
with its plugin working directory, and requires successful MCP initialization and
tool discovery before writing the output archive. CI runs this on macOS and Linux.
The suite release builder also validates launch configurations before packaging.

Do not distribute manually zipped older cache directories. A successful server
start by absolute path does not validate the installed configuration. For Desktop
acceptance, install the exact release ZIP, confirm its tool appears, and save a
synthetic receipt. Keep the existing fresh-profile UI acceptance requirement;
these protocol checks do not replace it.
