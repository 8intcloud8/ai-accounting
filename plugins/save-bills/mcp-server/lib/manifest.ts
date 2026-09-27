import fs from "node:fs";
import path from "node:path";

export interface ManifestRow {
  /** DD-MM-YYYY */
  date: string;
  vendor: string;
  subject: string;
  category: string;
  filename: string;
  gmailLink: string;
  foundVia: string;
  status: "saved" | "failed";
}

const HEADER = [
  "date",
  "vendor",
  "subject",
  "category",
  "filename",
  "gmail_link",
  "found_via",
  "status",
];

/** Neutralizes formula injection (CWE-1236) — vendor/subject come straight
 * from attacker-controlled email headers, and this file is meant to be
 * opened in Excel/Sheets, which treat a leading =, +, -, or @ as a formula. */
function neutralizeFormula(value: string): string {
  return /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
}

function csvEscape(value: string): string {
  const safe = neutralizeFormula(value);
  return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

/** Appends rows to <folderPath>/manifest.csv, writing the header only if the
 * file doesn't already exist (safe to call across multiple save_bills runs
 * into the same folder). */
export function appendManifestRows(folderPath: string, rows: ManifestRow[]): void {
  const manifestPath = path.join(folderPath, "manifest.csv");
  const isNew = !fs.existsSync(manifestPath);
  const lines: string[] = [];
  if (isNew) lines.push(HEADER.join(","));
  for (const row of rows) {
    lines.push(
      [
        row.date,
        row.vendor,
        row.subject,
        row.category,
        row.filename,
        row.gmailLink,
        row.foundVia,
        row.status,
      ]
        .map(csvEscape)
        .join(","),
    );
  }
  fs.appendFileSync(manifestPath, lines.join("\n") + "\n", "utf-8");
}
