import type { BillCategory } from "../src/types.js";

/** Folder-name / manifest label for a category. */
export function categoryLabel(category: BillCategory): string {
  if (category === "business") return "Business";
  if (category === "personal") return "Personal";
  return "Bills";
}
