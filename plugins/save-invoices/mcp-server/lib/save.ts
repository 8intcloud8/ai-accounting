import fs from "node:fs";
import path from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { mapWithConcurrency } from "./concurrency.js";
import { buildFilename, dedupeFilename } from "./filenames.js";
import { appendManifestRows, type ManifestRow } from "./manifest.js";
import { renderHtmlToPdf, wrapPlainTextAsHtml } from "./pdf.js";
import { expandHome } from "./paths.js";
import { toDisplayDate } from "./dates.js";
import { categoryLabel } from "./category.js";
import type {
  BillCategory,
  McpSaveBillItemInput,
  SaveBillsFailedItem,
  SaveBillsSavedItem,
  SaveBillsStructured,
} from "../src/types.js";

const SAVE_CONCURRENCY = Number(process.env.SAVE_CONCURRENCY ?? 5) || 5;
const DEFAULT_ROOT = process.env.BILLS_ROOT_DEFAULT ?? "~/Documents/Bills";
const MAX_MCP_ATTACHMENT_BYTES = 100 * 1024 * 1024;

function removeIfExists(p: string): void {
  try {
    fs.rmSync(p, { force: true });
  } catch {
    // best-effort cleanup only
  }
}

/** Retries `fn` once on failure, removing whatever `destPath` it may have
 * partially written so a failed file never squats on the correct filename
 * across retries/re-runs. Returns the failure reason if both attempts fail. */
async function attemptWithOneRetry(
  fn: () => Promise<void>,
  destPath: string,
): Promise<{ ok: true } | { ok: false; reason: string }> {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      await fn();
      return { ok: true };
    } catch (e) {
      removeIfExists(destPath);
      if (attempt === 1) {
        return { ok: false, reason: e instanceof Error ? e.message : String(e) };
      }
    }
  }
  return { ok: false, reason: "unreachable" };
}

interface ThreadOutcome {
  saved: SaveBillsSavedItem[];
  failed: SaveBillsFailedItem[];
  manifestRows: ManifestRow[];
  inlineConverted: boolean;
}

async function downloadMcpAttachment(downloadUrl: string, destPath: string): Promise<void> {
  const url = new URL(downloadUrl);
  if (url.protocol !== "https:" ||
      !/^[a-z0-9-]+\.oaiusercontent\.com$/i.test(url.hostname) ||
      !url.pathname.startsWith("/files/")) {
    throw new Error("Attachment URL is not an approved Gmail MCP file link.");
  }
  const response = await fetch(url, { redirect: "error", signal: AbortSignal.timeout(60_000) });
  if (!response.ok || !response.body) throw new Error(`Attachment download failed (${response.status}).`);
  const declaredSize = Number(response.headers.get("content-length"));
  if (declaredSize > MAX_MCP_ATTACHMENT_BYTES) throw new Error("Attachment exceeds 100 MB limit.");
  let bytes = 0;
  const limiter = new Transform({
    transform(chunk: Buffer, _encoding, callback) {
      bytes += chunk.length;
      callback(bytes > MAX_MCP_ATTACHMENT_BYTES ? new Error("Attachment exceeds 100 MB limit.") : null, chunk);
    },
  });
  await pipeline(
    Readable.fromWeb(response.body as Parameters<typeof Readable.fromWeb>[0]),
    limiter,
    fs.createWriteStream(destPath, { flags: "wx" }),
  );
  if (bytes === 0) throw new Error("Attachment download was empty.");
}

async function processMcpItem(
  item: McpSaveBillItemInput,
  categoryLbl: string,
  folderPath: string,
  usedFilenames: Set<string>,
): Promise<ThreadOutcome> {
  const { threadId, date: isoDate, vendor, subject, attachments } = item;
  const gmailLink = `https://mail.google.com/mail/u/0/#all/${threadId}`;
  const foundVia = item.foundVia.join(", ") || "gmail-mcp";
  const saved: SaveBillsSavedItem[] = [];
  const failed: SaveBillsFailedItem[] = [];
  const manifestRows: ManifestRow[] = [];
  let inlineConverted = false;

  function record(filename: string, result: { ok: true } | { ok: false; reason: string }) {
    manifestRows.push({
      date: toDisplayDate(isoDate), vendor, subject, category: categoryLbl,
      filename, gmailLink, foundVia, status: result.ok ? "saved" : "failed",
    });
    if (result.ok) saved.push({ vendor, date: isoDate, filename });
    else failed.push({ vendor, date: isoDate, subject, reason: result.reason });
  }

  if (attachments.length > 0) {
    for (const attachment of attachments) {
      const rawName = attachment.filename || "attachment";
      const dot = rawName.lastIndexOf(".");
      const filename = dedupeFilename(buildFilename({
        isoDate, vendor, subject,
        ext: dot < 0 ? "" : rawName.slice(dot),
        originalBaseName: dot < 0 ? rawName : rawName.slice(0, dot),
      }), usedFilenames);
      const destPath = path.join(folderPath, filename);
      record(filename, await attemptWithOneRetry(
        () => downloadMcpAttachment(attachment.downloadUrl, destPath), destPath,
      ));
    }
  } else {
    const filename = dedupeFilename(buildFilename({
      isoDate, vendor, subject, ext: ".pdf", originalBaseName: subject,
    }), usedFilenames);
    const destPath = path.join(folderPath, filename);
    const result = await attemptWithOneRetry(async () => {
      if (!item.html && !item.text) throw new Error("No inline email body was supplied by Gmail MCP.");
      await renderHtmlToPdf(item.html || wrapPlainTextAsHtml(item.text || "", subject), destPath);
      if (fs.statSync(destPath).size === 0) throw new Error("wrote 0 bytes");
    }, destPath);
    inlineConverted = result.ok;
    record(filename, result);
  }
  return { saved, failed, manifestRows, inlineConverted };
}

export async function runSaveBillsFromMcp(
  items: McpSaveBillItemInput[],
  category: BillCategory,
  dateRangeTag: string,
  rootFolder: string,
): Promise<SaveBillsStructured> {
  const resolvedRoot = path.resolve(expandHome(rootFolder?.trim() || DEFAULT_ROOT));
  const folderPath = path.resolve(resolvedRoot, categoryLabel(category), dateRangeTag);
  if (folderPath !== resolvedRoot && !folderPath.startsWith(resolvedRoot + path.sep)) {
    throw new Error(`Resolved save folder (${folderPath}) escapes root_folder (${resolvedRoot})`);
  }
  fs.mkdirSync(folderPath, { recursive: true });
  const usedFilenames = new Set<string>(fs.readdirSync(folderPath));
  const outcomes = await mapWithConcurrency(items, SAVE_CONCURRENCY, (item) =>
    processMcpItem(item, categoryLabel(category), folderPath, usedFilenames),
  );
  const saved = outcomes.flatMap((o) => o.saved);
  const failed = outcomes.flatMap((o) => o.failed);
  const manifestRows = outcomes.flatMap((o) => o.manifestRows);
  if (manifestRows.length > 0) appendManifestRows(folderPath, manifestRows);
  return {
    savedCount: saved.length,
    failedCount: failed.length,
    inlineConvertedCount: outcomes.filter((o) => o.inlineConverted).length,
    folderPath, saved, failed,
  };
}
