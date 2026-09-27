import { useMemo } from "react";
import type { BillResult } from "../types";
import styles from "../mcp-app.module.css";

interface BillTableProps {
  bills: BillResult[];
  selected: Set<string>;
  onToggle: (threadId: string) => void;
  onToggleAll: (ids: string[], checked: boolean) => void;
  filterText: string;
  onFilterChange: (text: string) => void;
  onOpenLink: (url: string) => void;
}

function matchesFilter(bill: BillResult, filter: string): boolean {
  if (!filter.trim()) return true;
  const needle = filter.toLowerCase();
  return (
    bill.vendor.toLowerCase().includes(needle) ||
    bill.subject.toLowerCase().includes(needle) ||
    bill.sender.email.toLowerCase().includes(needle) ||
    bill.date.includes(needle)
  );
}

export function BillTable({
  bills,
  selected,
  onToggle,
  onToggleAll,
  filterText,
  onFilterChange,
  onOpenLink,
}: BillTableProps) {
  const filtered = useMemo(() => bills.filter((b) => matchesFilter(b, filterText)), [bills, filterText]);
  const filteredIds = useMemo(() => filtered.map((b) => b.threadId), [filtered]);
  const allFilteredSelected = filteredIds.length > 0 && filteredIds.every((id) => selected.has(id));

  return (
    <div>
      <div className={styles.toolbar}>
        <label>
          <input
            type="checkbox"
            checked={allFilteredSelected}
            onChange={(e) => onToggleAll(filteredIds, e.target.checked)}
          />{" "}
          Select all
        </label>
        <span className={styles.counter}>{selected.size} selected</span>
        <div className={styles.toolbarSpacer} />
        <input
          type="text"
          className={styles.filterInput}
          placeholder="Filter by vendor, subject, sender…"
          value={filterText}
          onChange={(e) => onFilterChange(e.target.value)}
        />
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th></th>
              <th>Date</th>
              <th>Vendor</th>
              <th>Subject</th>
              <th>Attachment</th>
              <th>Found via</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((bill) => (
              <tr key={bill.threadId}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(bill.threadId)}
                    onChange={() => onToggle(bill.threadId)}
                  />
                </td>
                <td>{bill.date}</td>
                <td>{bill.vendor}</td>
                <td className={styles.subjectCell} title={bill.subject}>
                  {bill.subject}
                </td>
                <td>
                  {bill.isInline ? (
                    <span className={styles.badgeInline}>inline</span>
                  ) : (
                    <span className={styles.badgeAttachment} title={bill.attachments.join(", ")}>
                      {bill.attachments.length} file{bill.attachments.length === 1 ? "" : "s"}
                    </span>
                  )}
                </td>
                <td className={styles.foundVia}>{bill.foundVia.join(", ")}</td>
                <td>
                  <button type="button" className={styles.linkButton} onClick={() => onOpenLink(bill.gmailLink)}>
                    Open
                  </button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7}>No bills match this filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
