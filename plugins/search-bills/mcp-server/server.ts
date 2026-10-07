import {
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult, ReadResourceResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import fs from "node:fs/promises";
import path from "node:path";
import fsSync from "node:fs";
import { fileURLToPath } from "node:url";
import { consolidateBills } from "./lib/search.js";

// When running from source, the built UI lives in ./dist. When running as a
// bundle that itself sits inside dist/, the UI is a sibling. Accept both.
// import.meta.dirname needs Node 20.11+; derive it from import.meta.url so
// the server also starts on older Node runtimes.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIST_DIR = fsSync.existsSync(path.join(HERE, "mcp-app.html"))
  ? HERE
  : path.join(HERE, "dist");

const CATEGORY = z.enum(["personal", "business", "bills"]);
const ISO_DATE = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected YYYY-MM-DD");

const billResultSchema = z.object({
  threadId: z.string(),
  messageId: z.string(),
  date: z.string(),
  sender: z.object({ name: z.string(), email: z.string() }),
  vendor: z.string(),
  vendorDomain: z.string(),
  subject: z.string(),
  attachments: z.array(z.string()),
  isInline: z.boolean(),
  foundVia: z.array(z.string()),
  gmailLink: z.string(),
});

// Search candidates come from the caller's Gmail connector.

const candidateSchema = z.object({
  threadId: z.string(),
  messageId: z.string(),
  date: ISO_DATE,
  sender: z.object({ name: z.string(), email: z.string() }),
  subject: z.string(),
  attachmentFilenames: z.array(z.string()),
  foundVia: z.string(),
});

const searchBillsInput = {
  category: CATEGORY.describe(
    "personal, business, or bills (unlabelled). Business runs apply the personal-vendor exclusion filter.",
  ),
  date_from: ISO_DATE.describe("Start date, YYYY-MM-DD"),
  date_to: ISO_DATE.describe("End date, YYYY-MM-DD (inclusive)"),
  candidates: z
    .array(candidateSchema)
    .describe(
      "Every candidate occurrence found by your own multi-pass Gmail search (one entry per " +
        "matching thread per pass — the same thread can appear more than once with a " +
        "different found_via). This tool dedupes by thread, merges attachment filenames and " +
        "found-via tags, and (on a business run) applies the personal-vendor exclusion filter.",
    ),
};

const searchBillsOutput = {
  bills: z.array(billResultSchema),
  excluded: z.array(
    z.object({ vendor: z.string(), sender: z.string(), matchedRule: z.string() }),
  ),
  counts: z.object({
    total: z.number(),
    withAttachment: z.number(),
    inline: z.number(),
    vendorsCount: z.number(),
    excludedCount: z.number(),
  }),
  category: CATEGORY,
  dateFrom: z.string(),
  dateTo: z.string(),
  dateRangeTag: z.string(),
};

export function createServer(): McpServer {
  const server = new McpServer({ name: "bill-search-app", version: "1.0.0" });
  const resourceUri = "ui://bill-checklist/v2/mcp-app.html";

  registerAppTool(
    server,
    "search_bills",
    {
      title: "Search Bills",
      description:
        "Consolidates candidate bills/invoices/receipts you found via your own Gmail search " +
        "into a deduped, vendor-grouped checklist UI. This tool does not search Gmail itself — " +
        "pass every candidate occurrence you found (see the companion skill for the multi-pass " +
        "search strategy: keyword/attachment/label/inline/forwarded passes, then sender-domain " +
        "and synonym expansion, run until a full round adds nothing new). Business runs exclude " +
        "personal vendors.",
      inputSchema: searchBillsInput,
      outputSchema: searchBillsOutput,
      _meta: { ui: { resourceUri } },
    },
    async ({ category, date_from, date_to, candidates }): Promise<CallToolResult> => {
      const result = consolidateBills(candidates, category, date_from, date_to);
      const summary =
        `Found ${result.counts.total} bill(s) across ${result.counts.vendorsCount} vendor(s) ` +
        `(${result.counts.withAttachment} with attachments, ${result.counts.inline} inline)` +
        (result.category === "business"
          ? `. Excluded ${result.counts.excludedCount} personal-vendor result(s).`
          : ".");
      return {
        content: [{ type: "text", text: summary }],
        structuredContent: { ...result },
      };
    },
  );

  registerAppResource(
    server,
    resourceUri,
    resourceUri,
    { mimeType: RESOURCE_MIME_TYPE },
    async (): Promise<ReadResourceResult> => {
      const html = await fs.readFile(path.join(DIST_DIR, "mcp-app.html"), "utf-8");
      return {
        contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html }],
      };
    },
  );

  return server;
}
