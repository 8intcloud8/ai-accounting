export type BillCategory = "personal" | "business" | "bills";

export interface McpSaveBillItemInput {
  threadId: string;
  date: string;
  vendor: string;
  subject: string;
  foundVia: string[];
  attachments: Array<{ filename: string; downloadUrl: string }>;
  html?: string;
  text?: string;
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
