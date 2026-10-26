import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { expandHome } from "./paths.js";

function tokenFilePath(): string {
  return expandHome(process.env.MCP_AUTH_TOKEN_PATH ?? "~/.bill-search-app/mcp-token.txt");
}

/**
 * Shared-secret token that gates the /mcp HTTP endpoint. Generated once and
 * persisted on first run (set MCP_AUTH_TOKEN to pin a specific value
 * instead). Needed because the endpoint is meant to be tunneled to a chat
 * host as a custom connector — without this, anyone who reaches the URL (or
 * any page in the operator's own browser, given permissive CORS) could call
 * search_bills/save_bills using the operator's Gmail session.
 */
export function getOrCreateMcpToken(): string {
  if (process.env.MCP_AUTH_TOKEN) return process.env.MCP_AUTH_TOKEN;
  const p = tokenFilePath();
  if (fs.existsSync(p)) {
    const existing = fs.readFileSync(p, "utf-8").trim();
    if (existing) return existing;
  }
  const token = crypto.randomBytes(24).toString("base64url");
  fs.mkdirSync(path.dirname(p), { recursive: true, mode: 0o700 });
  fs.writeFileSync(p, token, { mode: 0o600 });
  return token;
}

function timingSafeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

/** Extracts a token from `Authorization: Bearer <token>` or a `?token=`
 * query param (query param support matters because some connector configs
 * can only supply a bare URL, not custom headers). */
export function extractRequestToken(req: {
  header(name: string): string | undefined;
  query: Record<string, unknown>;
}): string | undefined {
  const auth = req.header("authorization");
  if (auth?.startsWith("Bearer ")) return auth.slice(7);
  const q = req.query.token;
  return typeof q === "string" ? q : undefined;
}

export function isValidToken(provided: string | undefined, expected: string): boolean {
  return provided !== undefined && timingSafeEqual(provided, expected);
}
