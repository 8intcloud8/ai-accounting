import { execFile } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createTokenManager } from './token-manager.mjs';

const [packageRoot, python, helper] = process.argv.slice(2);
const manifest = JSON.parse(await readFile(resolve(packageRoot, 'package.json'), 'utf8'));
if (manifest.name !== '@xeroapi/xero-mcp-server' || manifest.version !== '0.0.17') {
  throw new Error('Unsupported Xero MCP runtime; expected reviewed version 0.0.17.');
}
function refresh() {
  return new Promise((resolveToken, reject) => {
    // Tokens travel only through a private child-process pipe, never MCP stdout.
    execFile(python, [helper, 'token'], { timeout: 45000, maxBuffer: 65536 }, (error, stdout) => {
      if (error) return reject(new Error('Xero token exchange failed.'));
      try { resolveToken(JSON.parse(stdout)); }
      catch { reject(new Error('Invalid token exchange response.')); }
    });
  });
}
let liveClient;
const manager = createTokenManager(refresh, {
  onToken: token => liveClient?.setTokenSet(token)
});
try {
  await manager.getToken();
  const { xeroClient } = await import(pathToFileURL(resolve(packageRoot, 'dist/clients/xero-client.js')));
  if (xeroClient.constructor.name !== 'BearerTokenXeroClient' ||
      typeof xeroClient.setTokenSet !== 'function' || typeof xeroClient.updateTenants !== 'function') {
    throw new Error('Xero MCP authentication interface changed.');
  }
  liveClient = xeroClient;
  xeroClient.setTokenSet(await manager.getToken());
  xeroClient.authenticate = async function () {
    this.setTokenSet(await manager.getToken());
    await this.updateTenants();
  };
  process.once('exit', () => manager.close());
  await import(pathToFileURL(resolve(packageRoot, 'dist/index.js')));
} catch {
  manager.close();
  console.error('Xero MCP startup failed. Check setup, runtime dependencies and authorization.');
  process.exitCode = 1;
}
