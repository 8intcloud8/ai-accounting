import type { SaveBillsStructured } from "../types";
import styles from "../mcp-app.module.css";

interface SaveSummaryProps {
  result: SaveBillsStructured;
  onBack: () => void;
}

export function SaveSummary({ result, onBack }: SaveSummaryProps) {
  return (
    <div className={styles.summary}>
      <div className={styles.summaryGrid}>
        <div className={styles.summaryStat}>
          <span className={styles.summaryStatValue}>{result.savedCount}</span>
          <span className={styles.summaryStatLabel}>Saved</span>
        </div>
        <div className={styles.summaryStat}>
          <span className={styles.summaryStatValue}>{result.failedCount}</span>
          <span className={styles.summaryStatLabel}>Failed</span>
        </div>
        <div className={styles.summaryStat}>
          <span className={styles.summaryStatValue}>{result.inlineConvertedCount}</span>
          <span className={styles.summaryStatLabel}>Inline → PDF</span>
        </div>
      </div>

      <div>
        <p className={styles.subtitle}>Saved to:</p>
        <div className={styles.folderPath}>{result.folderPath}</div>
      </div>

      {result.failed.length > 0 && (
        <div className={styles.failedList}>
          <strong className={styles.errorText}>Failed items:</strong>
          {result.failed.map((item, i) => (
            <div key={i} className={styles.failedItem}>
              {item.vendor} ({item.date}) — {item.subject}: {item.reason}
            </div>
          ))}
        </div>
      )}

      <button type="button" className={styles.buttonSecondary} onClick={onBack}>
        Back to list
      </button>
    </div>
  );
}
