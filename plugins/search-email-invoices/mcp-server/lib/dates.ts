/** Compact folder-name tag, e.g. "2024-07-01_2025-06-30". */
export function buildDateRangeTag(dateFrom: string, dateTo: string): string {
  return `${dateFrom}_${dateTo}`;
}

/** DD-MM-YYYY, for filenames and manifest rows. */
export function toDisplayDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-");
  return `${d}-${m}-${y}`;
}
