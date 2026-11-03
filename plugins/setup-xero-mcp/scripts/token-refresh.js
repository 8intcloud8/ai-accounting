#!/usr/bin/env node
const { spawn } = require('node:child_process');
const path = require('node:path');
const windows = process.platform === 'win32';
const child = spawn(windows ? 'py' : 'python3', [
  ...(windows ? ['-3'] : []), path.join(__dirname, 'xero_auth.py'), 'serve'
], { stdio: 'inherit' });
child.on('error', () => { console.error('Python 3 launcher unavailable.'); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
