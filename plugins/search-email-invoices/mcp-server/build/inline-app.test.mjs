import assert from 'node:assert/strict';
import test from 'node:test';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { createServer, UI_URI } from '../server.ts';

test('search shows its results inline and keeps bill details out of chat text', async () => {
  const server = createServer();
  const client = new Client({ name: 'browser-only-test', version: '1.0.0' });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  try {
    const { tools } = await client.listTools();
    const search = tools.find(tool => tool.name === 'search_email_invoices');
    assert.ok(search);
    assert.equal(search._meta.ui.resourceUri, UI_URI);
    assert.equal(search._meta['ui/resourceUri'], UI_URI);
    const { resources } = await client.listResources();
    assert.deepEqual(resources.map(r => r.uri), [UI_URI]);
    const page = (await client.readResource({ uri: UI_URI })).contents[0];
    assert.equal(page.mimeType, 'text/html;profile=mcp-app');
    assert.match(page.text, /ui\/message/);
    assert.doesNotMatch(page.text, /\.innerHTML\s*=|insertAdjacentHTML|outerHTML/);
    const result = await client.callTool({
      name: 'search_email_invoices',
      arguments: {
        category: 'bills', date_from: '2026-07-01', date_to: '2026-09-30',
        candidates: [{
          threadId: 'fixture-thread', messageId: 'fixture-message',
          date: '2026-08-01', sender: { name: 'Fixture Vendor', email: 'billing@example.com' },
          subject: 'PRIVATE-FIXTURE-INVOICE', attachmentFilenames: ['private-fixture.pdf'],
          foundVia: 'fixture',
        }],
        accounts: ['owner@example.com'], destination: '/tmp/ws/invoices',
      },
    });
    assert.equal(result.isError, undefined);
    assert.equal(result.structuredContent.bills.length, 1);
    assert.deepEqual(result.structuredContent.accounts, ['owner@example.com']);
    assert.equal(result.structuredContent.destination, '/tmp/ws/invoices');
    assert.ok(result.content.every(block => block.type === 'text'));
    assert.ok(!JSON.stringify(result.content).includes('PRIVATE-FIXTURE-INVOICE'));
    assert.ok(!JSON.stringify(result.content).includes('private-fixture.pdf'));
    assert.ok(!JSON.stringify(result.content).includes('Fixture Vendor'));
  } finally {
    await client.close();
    await server.close();
  }
});
