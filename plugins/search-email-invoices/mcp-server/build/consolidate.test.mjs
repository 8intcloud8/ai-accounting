import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

process.env.CODEX_HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-home-'));
const { consolidateBills } = await import('../lib/search.ts');
const { loadPersonalVendors, USER_VENDORS_PATH } = await import('../lib/vendors.ts');

const sender = { name: 'Harbour Hotel', email: 'stay@harbour.example' };
const entry = (messageId, date, files, foundVia = 'keyword', threadId = 't1') =>
  ({ threadId, messageId, date, sender, subject: 'Your stay', attachmentFilenames: files, foundVia });

test('saves the invoice message, not the earlier booking confirmation', () => {
  const r = consolidateBills([
    entry('booking', '2026-07-02', []),
    entry('invoice', '2026-07-09', ['tax-invoice.pdf']),
    entry('thanks', '2026-07-10', []),
  ], 'bills', '2026-07-01', '2026-09-30');
  assert.equal(r.bills[0].messageId, 'invoice');
  assert.deepEqual(r.bills[0].messageIds, ['booking', 'invoice', 'thanks']);
  assert.deepEqual(r.bills[0].attachments, ['tax-invoice.pdf']);
});

test('inline thread saves its latest message', () => {
  const r = consolidateBills([entry('a', '2026-07-02', []), entry('b', '2026-07-05', [])],
    'bills', '2026-07-01', '2026-09-30');
  assert.equal(r.bills[0].messageId, 'b');
});

test('drops messages dated outside the period', () => {
  const r = consolidateBills([
    entry('old', '2026-06-30', ['june.pdf']),
    entry('in', '2026-07-01', []),
    entry('late', '2026-10-01', ['oct.pdf'], 'k', 't2'),
  ], 'bills', '2026-07-01', '2026-09-30');
  assert.equal(r.counts.outOfRange, 2);
  assert.deepEqual(r.bills.map(b => b.messageId), ['in']);
});

test('exclusions live outside the plugin and ignore entries under 3 characters', () => {
  fs.writeFileSync(USER_VENDORS_PATH, JSON.stringify({ personalVendors: ['au', 'harbour'], suppressed: [] }));
  assert.ok(USER_VENDORS_PATH.startsWith(process.env.CODEX_HOME));
  assert.deepEqual(loadPersonalVendors(), ['harbour']);
  const r = consolidateBills([entry('m', '2026-07-03', ['x.pdf'])], 'business', '2026-07-01', '2026-09-30');
  assert.equal(r.counts.excludedCount, 1);
});
