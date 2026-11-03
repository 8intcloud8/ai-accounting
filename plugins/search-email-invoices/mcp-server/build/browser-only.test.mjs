import assert from 'node:assert/strict';
import test from 'node:test';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { createServer } from '../server.ts';

test('search exposes data without advertising or returning an inline app', async () => {
  const server = createServer();
  const client = new Client({ name: 'browser-only-test', version: '1.0.0' });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  try {
    const { tools } = await client.listTools();
    const search = tools.find(tool => tool.name === 'search_bills');
    assert.ok(search);
    assert.equal(search._meta, undefined);
    assert.equal(server.server.getCapabilities().resources, undefined);
    const result = await client.callTool({
      name: 'search_bills',
      arguments: {
        category: 'bills', date_from: '2026-07-01', date_to: '2026-09-30',
        candidates: [{
          threadId: 'fixture-thread', messageId: 'fixture-message',
          date: '2026-08-01', sender: { name: 'Fixture Vendor', email: 'billing@example.com' },
          subject: 'PRIVATE-FIXTURE-INVOICE', attachmentFilenames: ['private-fixture.pdf'],
          foundVia: 'fixture',
        }],
      },
    });
    assert.equal(result.isError, undefined);
    assert.equal(result.structuredContent.bills.length, 1);
    assert.equal(result._meta, undefined);
    assert.ok(result.content.every(block => block.type === 'text'));
    assert.ok(!JSON.stringify(result.content).includes('PRIVATE-FIXTURE-INVOICE'));
    assert.ok(!JSON.stringify(result.content).includes('private-fixture.pdf'));
    assert.ok(!JSON.stringify(result.content).includes('Fixture Vendor'));
  } finally {
    await client.close();
    await server.close();
  }
});
