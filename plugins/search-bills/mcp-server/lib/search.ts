import { matchPersonalVendor, loadPersonalVendors } from "./vendors.js";
import { buildDateRangeTag } from "./dates.js";
import { domainOf } from "./domain.js";
import type {
  BillCandidateInput,
  BillCategory,
  BillResult,
  ExcludedBill,
  SearchBillsStructured,
} from "../src/types.js";

/**
 * Consolidates candidate occurrences (gathered by the agent via its own
 * Gmail tool calls) into the deduped, vendor-grouped checklist: groups by
 * thread, merges attachment filenames and found-via tags across every
 * occurrence of a thread, picks the earliest message as the display
 * primary, and — on a business run — applies the personal-vendor
 * exclusion filter. No Gmail access here; this is pure local logic.
 */
export function consolidateBills(
  candidates: BillCandidateInput[],
  category: BillCategory,
  dateFrom: string,
  dateTo: string,
): SearchBillsStructured {
  const byThread = new Map<string, BillCandidateInput[]>();
  for (const c of candidates) {
    const list = byThread.get(c.threadId) ?? [];
    list.push(c);
    byThread.set(c.threadId, list);
  }

  const vendors = category === "business" ? loadPersonalVendors() : [];
  const bills: BillResult[] = [];
  const excluded: ExcludedBill[] = [];

  for (const [threadId, entries] of byThread) {
    const primary = entries.reduce((a, b) => (a.date <= b.date ? a : b));
    const attachments = Array.from(new Set(entries.flatMap((e) => e.attachmentFilenames)));
    const foundVia = Array.from(new Set(entries.map((e) => e.foundVia)));
    const domain = domainOf(primary.sender.email);

    if (category === "business") {
      const matched = matchPersonalVendor(primary.sender, vendors);
      if (matched) {
        excluded.push({
          vendor: primary.sender.name || domain,
          sender: `${primary.sender.name} <${primary.sender.email}>`,
          matchedRule: matched,
        });
        continue;
      }
    }

    bills.push({
      threadId,
      messageId: primary.messageId,
      date: primary.date,
      sender: primary.sender,
      vendor: primary.sender.name || domain,
      vendorDomain: domain,
      subject: primary.subject,
      attachments,
      isInline: attachments.length === 0,
      foundVia,
      gmailLink: `https://mail.google.com/mail/u/0/#all/${threadId}`,
    });
  }

  bills.sort((a, b) => a.vendor.localeCompare(b.vendor) || a.date.localeCompare(b.date));
  const withAttachment = bills.filter((b) => !b.isInline).length;
  const vendorsCount = new Set(bills.map((b) => b.vendorDomain)).size;

  return {
    bills,
    excluded,
    counts: {
      total: bills.length,
      withAttachment,
      inline: bills.length - withAttachment,
      vendorsCount,
      excludedCount: excluded.length,
    },
    category,
    dateFrom,
    dateTo,
    dateRangeTag: buildDateRangeTag(dateFrom, dateTo),
  };
}
