/**
 * Entry point for running the bill-search-app MCP server.
 * Run with: npm run serve            (streamable HTTP on $PORT, default 3001)
 * Or:       npm run serve:stdio      (stdio transport)
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import cors from "cors";
import express, { type Request, type Response } from "express";
import { createServer } from "./server.js";
import { getOrCreateMcpToken, extractRequestToken, isValidToken } from "./lib/mcpAuth.js";

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

async function startStreamableHTTPServer(
  factory: () => McpServer,
): Promise<void> {
  const port = parseInt(process.env.PORT ?? "3001", 10);
  // Loopback by default — this server is meant to be reached via an
  // explicit tunnel (see README), not exposed on the LAN by accident.
  const host = process.env.HOST ?? "127.0.0.1";
  const token = getOrCreateMcpToken();

  const app = express();
  app.use(cors());
  app.use(express.json());

  app.all("/mcp", async (req: Request, res: Response) => {
    const provided = extractRequestToken(req);
    if (!isValidToken(provided, token)) {
      res.status(401).json({
        jsonrpc: "2.0",
        error: { code: -32001, message: "Unauthorized — missing or invalid token" },
        id: null,
      });
      return;
    }

    const server = factory();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
    });

    res.on("close", () => {
      transport.close().catch(() => {});
      server.close().catch(() => {});
    });

    try {
      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
    } catch (error) {
      console.error("MCP error:", errorMessage(error));
      if (!res.headersSent) {
        res.status(500).json({
          jsonrpc: "2.0",
          error: { code: -32603, message: "Internal server error" },
          id: null,
        });
      }
    }
  });

  const httpServer = app.listen(port, host, () => {
    console.log(`bill-search-app listening on http://${host}:${port}/mcp`);
    console.log(`Auth token (required — append ?token=... or send Authorization: Bearer ...):`);
    console.log(`  ${token}`);
  });

  const shutdown = () => {
    console.log("\nShutting down...");
    httpServer.close(() => process.exit(0));
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

async function startStdioServer(factory: () => McpServer): Promise<void> {
  await factory().connect(new StdioServerTransport());
}

async function main() {
  if (process.argv.includes("--stdio")) {
    await startStdioServer(createServer);
  } else {
    await startStreamableHTTPServer(createServer);
  }
}

main().catch((e) => {
  console.error(errorMessage(e));
  process.exit(1);
});
