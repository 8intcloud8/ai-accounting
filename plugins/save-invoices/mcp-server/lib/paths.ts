import os from "node:os";
import path from "node:path";

/** Expands a leading `~` to the user's home directory. Relative paths are
 * left as-is (resolved against process.cwd() by the caller/fs). */
export function expandHome(p: string): string {
  if (p === "~") return os.homedir();
  if (p.startsWith("~/")) return path.join(os.homedir(), p.slice(2));
  return p;
}
