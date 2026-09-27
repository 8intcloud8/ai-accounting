const AMOUNT_PATTERN = /(?:AUD|NZD|USD|A\$|NZ\$|US\$|\$)\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)/gi;
const TOTAL_CONTEXT = /\b(total|amount due|balance|amount owing|payable)\b/i;
const CONTEXT_WINDOW = 20;

/**
 * Best-effort dollar amount extraction from a subject/snippet, for
 * filenames. A subject can contain more than one figure (e.g. a discount
 * followed by the real total) — prefer a match near "total"/"amount due"/
 * "balance", else fall back to the last match (totals conventionally read
 * after any discount), else the only match. Returns e.g. "62.22", or null.
 */
export function extractAmount(text: string): string | null {
  const matches = [...text.matchAll(AMOUNT_PATTERN)];
  if (matches.length === 0) return null;
  const withContext = matches.find((m) =>
    TOTAL_CONTEXT.test(text.slice(Math.max(0, (m.index ?? 0) - CONTEXT_WINDOW), m.index ?? 0)),
  );
  const chosen = withContext ?? matches[matches.length - 1];
  return chosen[1].replace(/,/g, "");
}
