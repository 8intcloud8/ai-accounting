import styles from "../mcp-app.module.css";

export function ProgressState({ label }: { label: string }) {
  return (
    <div className={styles.progress}>
      <div className={styles.spinner} />
      <p>{label}</p>
    </div>
  );
}
