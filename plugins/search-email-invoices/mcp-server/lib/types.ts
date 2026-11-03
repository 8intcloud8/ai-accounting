/** Shared types between the server (tool handlers) and the UI resource. */

export type BillCategory = "personal" | "business" | "bills";

export interface BillSender {
  name: string;
  email: string;
}

export interface BillResult {
  threadId: string;
  messageId: string;
  /** YYYY-MM-DD */
  date: string;
  sender: BillSender;
  /** Display vendor name (sender's display name, falling back to domain) */
  vendor: string;
  /** Grouping key — the sender's domain, lowercased */
  vendorDomain: string;
  subject: string;
  /** Attachment filenames; empty when inline (no attachment) */
  attachments: string[];
  isInline: boolean;
  /** Which search pass(es) matched this thread, e.g. ["keyword", "sender:aws.amazon.com"] */
  foundVia: string[];
  gmailLink: string;
}

/**
 * One occurrence of a candidate bill found by the agent's own Gmail search
 * pass. search_bills takes an array of these (possibly several per thread,
 * one per matching pass) and consolidates/dedupes/filters them — it never
 * calls Gmail itself, since a standalone MCP server has no way to reach an
 * already-connected Gmail MCP connector.
 */
export interface BillCandidateInput {
  threadId: string;
  messageId: string;
  /** YYYY-MM-DD */
  date: string;
  sender: BillSender;
  subject: string;
  /** Attachment filenames on this message; empty if none */
  attachmentFilenames: string[];
  /** Which pass found this occurrence, e.g. "keyword", "sender:aws.amazon.com" */
  foundVia: string;
}

export interface ExcludedBill {
  vendor: string;
  sender: string;
  matchedRule: string;
}

export interface SearchBillsCounts {
  total: number;
  withAttachment: number;
  inline: number;
  vendorsCount: number;
  excludedCount: number;
}

export interface SearchBillsStructured {
  bills: BillResult[];
  excluded: ExcludedBill[];
  counts: SearchBillsCounts;
  category: BillCategory;
  dateFrom: string;
  dateTo: string;
  /** Compact range tag used in folder names, e.g. "2024-07-01_2025-06-30" */
  dateRangeTag: string;
}

export interface SaveBillsFailedItem {
  vendor: string;
  date: string;
  subject: string;
  reason: string;
}

export interface SaveBillsSavedItem {
  vendor: string;
  date: string;
  filename: string;
}

export interface SaveBillsStructured {
  savedCount: number;
  failedCount: number;
  inlineConvertedCount: number;
  folderPath: string;
  saved: SaveBillsSavedItem[];
  failed: SaveBillsFailedItem[];
}
