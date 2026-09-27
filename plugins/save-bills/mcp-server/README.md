# Save Bills MCP server

See the root README for installation, configuration, privacy limitations, and usage.

```sh
npm ci
npm run typecheck
npm test
npm run build
./launch.sh --stdio
```

Only `save_bills` is exposed. Attachment saving uses host-supplied temporary links; inline conversion uses Puppeteer. The server does not log into Gmail or upload to accounting services.
