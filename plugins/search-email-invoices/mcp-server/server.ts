import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { consolidateBills } from "./lib/search.js";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// The inline checklist view sits next to server.ts, one level above the dist/ bundle.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE_PATH = [path.join(HERE, "checklist-app.html"), path.join(HERE, "..", "checklist-app.html")]
  .find((p) => fs.existsSync(p));

export const UI_URI = "ui://email-invoices/checklist.html";
const UI_MIME = "text/html;profile=mcp-app";

const CATEGORY = z.enum(["personal", "business", "bills"]);
const ISO_DATE = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected YYYY-MM-DD");

const billResultSchema = z.object({
  threadId: z.string(),
  messageId: z.string(),
  messageIds: z.array(z.string()),
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

const searchEmailInvoicesInput = {
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
  accounts: z
    .array(z.string())
    .optional()
    .describe("Gmail addresses that were searched; the checklist opens links in that mailbox."),
  destination: z
    .string()
    .optional()
    .describe("Folder the checklist offers for saving, e.g. <workspace>/invoices."),
};

const searchEmailInvoicesOutput = {
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
    outOfRange: z.number(),
  }),
  category: CATEGORY,
  dateFrom: z.string(),
  dateTo: z.string(),
  dateRangeTag: z.string(),
  accounts: z.array(z.string()),
  destination: z.string(),
};

export function createServer(): McpServer {
  const server = new McpServer({ name: "bill-search-app", version: "1.0.0" });
  // The checklist is shown inline in the chat as an MCP App: the tool names the view.
  server.registerResource(
    "Invoice checklist",
    UI_URI,
    { mimeType: UI_MIME, description: "Inline checklist of the invoices found in Gmail" },
    async () => ({
      contents: [{ uri: UI_URI, mimeType: UI_MIME, text: fs.readFileSync(PAGE_PATH ?? "checklist-app.html", "utf8"),
        _meta: { ui: { prefersBorder: true } } }],
    }),
  );
  server.registerTool(
    "search_email_invoices",
    {
      title: "Search Email Invoices",
      description:
        "Consolidates candidate bills/invoices/receipts you found via your own Gmail search " +
        "and shows them inline in the chat as a checklist the user ticks and saves from. Never " +
        "repeat its bill payload in chat. This tool does not search Gmail itself — " +
        "pass every candidate occurrence you found (see the companion skill for the multi-pass " +
        "search strategy: keyword/attachment/label/inline/forwarded passes, then sender-domain " +
        "and synonym expansion, run until a full round adds nothing new). Business runs exclude " +
        "personal vendors.",
      inputSchema: searchEmailInvoicesInput,
      outputSchema: searchEmailInvoicesOutput,
      _meta: { ui: { resourceUri: UI_URI, visibility: ["model", "app"] }, "ui/resourceUri": UI_URI },
      // Runs on this machine only: no network, no writes, no data leaves the host.
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async ({ category, date_from, date_to, candidates, accounts, destination }): Promise<CallToolResult> => {
      const result = consolidateBills(candidates, category, date_from, date_to);
      const summary =
        `Found ${result.counts.total} bill(s) across ${result.counts.vendorsCount} vendor(s) ` +
        `(${result.counts.withAttachment} with attachments, ${result.counts.inline} inline)` +
        (result.category === "business"
          ? `. Excluded ${result.counts.excludedCount} personal-vendor result(s).`
          : ".") +
        " The checklist is shown to the user inline; do not list the bills in chat.";
      return {
        content: [{ type: "text", text: summary }],
        structuredContent: { ...result, accounts: accounts ?? [], destination: destination ?? "" },
      };
    },
  );

  return server;
}
