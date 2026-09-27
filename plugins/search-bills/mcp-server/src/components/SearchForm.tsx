import type { BillCategory } from "../types";
import styles from "../mcp-app.module.css";

export interface SearchArgs {
  category: BillCategory;
  dateFrom: string;
  dateTo: string;
}

interface SearchFormProps {
  args: SearchArgs;
  onChange: (args: SearchArgs) => void;
}

/** Fully controlled — state lives in the parent so it stays in sync with
 * whatever args the host originally called search_bills with. */
export function SearchForm({ args, onChange }: SearchFormProps) {
  return (
    <div className={styles.searchForm}>
      <div className={styles.field}>
        <label htmlFor="category">Category</label>
        <select
          id="category"
          value={args.category}
          onChange={(e) => onChange({ ...args, category: e.target.value as BillCategory })}
        >
          <option value="personal">Personal</option>
          <option value="business">Business</option>
          <option value="bills">Bills (unlabelled)</option>
        </select>
      </div>
      <div className={styles.field}>
        <label htmlFor="date_from">From</label>
        <input
          id="date_from"
          type="date"
          value={args.dateFrom}
          onChange={(e) => onChange({ ...args, dateFrom: e.target.value })}
        />
      </div>
      <div className={styles.field}>
        <label htmlFor="date_to">To</label>
        <input
          id="date_to"
          type="date"
          value={args.dateTo}
          onChange={(e) => onChange({ ...args, dateTo: e.target.value })}
        />
      </div>
    </div>
  );
}
