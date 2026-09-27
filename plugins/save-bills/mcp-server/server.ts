import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { runSaveBillsFromMcp } from "./lib/save.js";

const CATEGORY = z.enum(["personal", "business", "bills"]);
const ISO_DATE = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected YYYY-MM-DD");
const DATE_RANGE_TAG = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}$/, "expected YYYY-MM-DD_YYYY-MM-DD");

const saveBillsInput = {
  items: z.array(z.object({
    threadId: z.string().regex(/^[a-f0-9]+$/i),
    date: ISO_DATE,
    vendor: z.string().min(1).max(256),
    subject: z.string().max(2048),
    foundVia: z.array(z.string().max(100)),
    attachments: z.array(z.object({
      filename: z.string().max(255),
      downloadUrl: z.url(),
    })).max(20),
    html: z.string().max(2_000_000).optional(),
    text: z.string().max(2_000_000).optional(),
  })).min(1).max(5).describe(
    "Up to five selected Gmail threads. Pass Gmail MCP file_uri.download_url links for " +
      "attachments, or an inline HTML/text body when there is no attachment.",
  ),
  category: CATEGORY,
  date_range: DATE_RANGE_TAG,
  root_folder: z.string().describe(
    "Base path; <category>/<date_range> subfolders are created under it",
  ),
};

const saveBillsOutput = {
  savedCount: z.number(),
  failedCount: z.number(),
  inlineConvertedCount: z.number(),
  folderPath: z.string(),
  saved: z.array(z.object({ vendor: z.string(), date: z.string(), filename: z.string() })),
  failed: z.array(
    z.object({ vendor: z.string(), date: z.string(), subject: z.string(), reason: z.string() }),
  ),
};

export function createServer(): McpServer {
  const server = new McpServer({ name: "save-bills", version: "1.0.0" });

  server.registerTool(
    "save_bills",
    {
      title: "Save Bills",
      description:
        "Save selected Gmail bills without a second Gmail login. Streams attachments from " +
        "short-lived Gmail MCP oaiusercontent.com links directly to disk, or renders inline " +
        "email HTML to PDF with JavaScript disabled. Verifies non-empty writes, retries once, " +
        "deduplicates filenames, and appends manifest.csv. Maximum five threads per call.",
      inputSchema: saveBillsInput,
      outputSchema: saveBillsOutput,
    },
    async ({ items, category, date_range, root_folder }): Promise<CallToolResult> => {
      const result = await runSaveBillsFromMcp(items, category, date_range, root_folder);
      return {
        content: [{
          type: "text",
          text:
            `Saved ${result.savedCount} file(s) from ${items.length} selected thread(s) ` +
            `to ${result.folderPath}; ${result.failedCount} failed.`,
        }],
        structuredContent: { ...result },
      };
    },
  );

  return server;
}
