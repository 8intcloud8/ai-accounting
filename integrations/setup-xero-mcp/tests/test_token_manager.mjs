import test from 'node:test';
import assert from 'node:assert/strict';
import { createTokenManager } from '../scripts/token-manager.mjs';

function fixture(refresh, onToken = () => {}) {
  let clock = 0, scheduled;
  const manager = createTokenManager(refresh, {
    now: () => clock, onError: () => {}, onToken,
    schedule: (fn, ms) => { scheduled = {fn, ms}; return 1; }, cancel: () => {}
  });
  return { manager, tick(ms) { clock += ms; }, get scheduled() { return scheduled; } };
}

test('refreshes two minutes before expiry and delivers new token to running client', async () => {
  let calls = 0; const delivered = [];
  const f = fixture(async () => ({access_token: `token-${++calls}`, expires_in: 1800}), token => delivered.push(token.access_token));
  assert.equal((await f.manager.getToken()).access_token, 'token-1');
  assert.equal(f.scheduled.ms, 1680000);
  f.tick(1680000);
  f.scheduled.fn();
  assert.equal((await f.manager.getToken()).access_token, 'token-2');
  assert.deepEqual(delivered, ['token-1', 'token-2']);
  assert.equal(calls, 2);
  f.manager.close();
});

test('concurrent tool calls share one token rotation', async () => {
  let calls = 0;
  const f = fixture(async () => { calls++; await new Promise(resolve => setImmediate(resolve)); return {access_token: 'fresh', expires_in: 1800}; });
  const tokens = await Promise.all(Array.from({length: 12}, () => f.manager.getToken()));
  assert.equal(calls, 1);
  assert.ok(tokens.every(token => token.access_token === 'fresh'));
  f.manager.close();
});

test('transient failure retries while valid token remains usable; expired tokens blocked', async () => {
  let calls = 0;
  const f = fixture(async () => { if (++calls > 1) throw Error('offline'); return {access_token: 'first', expires_in: 1800}; });
  await f.manager.getToken();
  f.tick(1680000);
  assert.equal((await f.manager.getToken()).access_token, 'first');
  assert.equal(f.scheduled.ms, 10000);
  f.tick(120001);
  await assert.rejects(f.manager.getToken(), /authorization unavailable/);
  f.manager.close();
});

test('refresh on first request after sleep and stop timers on close', async () => {
  let calls = 0;
  const f = fixture(async () => ({access_token: `t${++calls}`, expires_in: 1800}));
  await f.manager.getToken();
  f.tick(7200000);
  assert.equal((await f.manager.getToken()).access_token, 't2');
  f.manager.close();
  await assert.rejects(f.manager.getToken(), /stopped/);
});
