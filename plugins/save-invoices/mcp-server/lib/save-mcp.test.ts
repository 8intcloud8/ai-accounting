import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { runSaveBillsFromMcp } from "./save.js";

test("MCP save streams attachments, dedupes filenames, and writes manifest", async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "bill-mcp-save-"));
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return new Response("PDF bytes", { headers: { "content-length": "9" } });
  };
  try {
    const item = {
      threadId: "thread1", date: "2026-09-15", vendor: "Vendor", subject: "Invoice",
      foundVia: ["keyword"],
      attachments: [{ filename: "invoice.pdf", downloadUrl: "https://sdmntprcentralus.oaiusercontent.com/files/example/raw" }],
    };
    const result = await runSaveBillsFromMcp([item, { ...item, threadId: "thread2" }], "business", "2026-09-01_2026-09-30", temp);
    assert.equal(result.savedCount, 2);
    assert.equal(result.failedCount, 0);
    assert.equal(calls, 2);
    assert.notEqual(result.saved[0].filename, result.saved[1].filename);
    for (const saved of result.saved) assert.equal(fs.readFileSync(path.join(result.folderPath, saved.filename), "utf8"), "PDF bytes");
    assert.equal(fs.readFileSync(path.join(result.folderPath, "manifest.csv"), "utf8").match(/saved/g)?.length, 2);
  } finally {
    globalThis.fetch = originalFetch;
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test("MCP save rejects foreign links and cleans up empty downloads after one retry", async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "bill-mcp-fail-"));
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response(""); };
  try {
    const base = {
      date: "2026-09-15", vendor: "Vendor", subject: "Invoice", foundVia: ["keyword"],
    };
    const result = await runSaveBillsFromMcp([
      { ...base, threadId: "bad", attachments: [{ filename: "bad.pdf", downloadUrl: "https://example.com/files/malicious" }] },
      { ...base, threadId: "empty", attachments: [{ filename: "empty.pdf", downloadUrl: "https://sdmntprcentralus.oaiusercontent.com/files/empty/raw" }] },
    ], "business", "2026-09-01_2026-09-30", temp);
    assert.equal(result.savedCount, 0);
    assert.equal(result.failedCount, 2);
    assert.equal(calls, 2);
    assert.deepEqual(fs.readdirSync(result.folderPath), ["manifest.csv"]);
  } finally {
    globalThis.fetch = originalFetch;
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
