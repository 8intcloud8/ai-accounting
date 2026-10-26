import { toDisplayDate } from "./dates.js";
import { extractAmount } from "./amount.js";

export function sanitizeVendor(vendor: string): string {
  return vendor
    .normalize("NFKD")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

function sanitizeFilenamePart(s: string): string {
  return s.replace(/[/\\?%*:|"<>]/g, "-").trim();
}

/**
 * `DD-MM-YYYY_vendor_amount.ext` when an amount is readable from the
 * subject, else `DD-MM-YYYY_vendor_original-filename.ext`.
 */
export function buildFilename(params: {
  isoDate: string;
  vendor: string;
  subject: string;
  /** Include the leading dot, e.g. ".pdf" */
  ext: string;
  /** Attachment filename without extension, or a sanitized subject for inline PDFs */
  originalBaseName: string;
}): string {
  const displayDate = toDisplayDate(params.isoDate);
  const vendorPart = sanitizeVendor(params.vendor) || "Unknown";
  const amount = extractAmount(params.subject);
  const suffix = amount ?? (sanitizeFilenamePart(params.originalBaseName) || "file");
  // ext comes from the attacker-controlled attachment filename — sanitize it
  // too, not just baseName/vendor (defense in depth even though today's
  // extraction logic can't smuggle a path separator into it).
  const ext = sanitizeFilenamePart(params.ext);
  return `${displayDate}_${vendorPart}_${suffix}${ext}`;
}

/** Appends "-2", "-3", ... before the extension until the name is unique
 * within `used`, then registers it. */
export function dedupeFilename(filename: string, used: Set<string>): string {
  if (!used.has(filename)) {
    used.add(filename);
    return filename;
  }
  const dot = filename.lastIndexOf(".");
  const base = dot === -1 ? filename : filename.slice(0, dot);
  const ext = dot === -1 ? "" : filename.slice(dot);
  let n = 2;
  let candidate = `${base}-${n}${ext}`;
  while (used.has(candidate)) {
    n++;
    candidate = `${base}-${n}${ext}`;
  }
  used.add(candidate);
  return candidate;
}
