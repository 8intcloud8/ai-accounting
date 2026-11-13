import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { BillSender } from "./types.js";

// Each installation starts with no personal-vendor assumptions.
const DEFAULT_PERSONAL_VENDORS: string[] = [];

/** Entries shorter than this would match almost every sender (e.g. "au"). */
export const MIN_ENTRY_LENGTH = 3;

/** The user's exclusions live outside the plugin so reinstalling or upgrading keeps them. */
export const USER_VENDORS_PATH = path.join(
  process.env.CODEX_HOME ?? path.join(os.homedir(), ".codex"),
  "accounting-personal-vendors.json",
);

/** Older installs kept the file inside the plugin; read it until the user's file exists.
 * Both lib/vendors.ts and dist/server.mjs sit two levels below the plugin root. */
const LEGACY_VENDORS_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "data",
  "personal-vendors.json",
);

interface UserVendorFile {
  /** Entries the user added on top of the shipped list. */
  personalVendors: string[];
  /** Shipped entries the user turned off. */
  suppressed: string[];
}

function readShippedVendors(): string[] {
  const configPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "vendors.config.json");
  try {
    const raw = JSON.parse(fs.readFileSync(configPath, "utf-8"));
    if (Array.isArray(raw.personalVendors) && raw.personalVendors.length > 0) {
      return raw.personalVendors;
    }
  } catch {
    // fall through to default
  }
  return DEFAULT_PERSONAL_VENDORS;
}

function readUserFile(): UserVendorFile {
  const file = fs.existsSync(USER_VENDORS_PATH) ? USER_VENDORS_PATH : LEGACY_VENDORS_PATH;
  try {
    const raw = JSON.parse(fs.readFileSync(file, "utf-8"));
    return {
      personalVendors: Array.isArray(raw.personalVendors) ? raw.personalVendors : [],
      suppressed: Array.isArray(raw.suppressed) ? raw.suppressed : [],
    };
  } catch {
    return { personalVendors: [], suppressed: [] };
  }
}

function writeUserFile(data: UserVendorFile): void {
  fs.mkdirSync(path.dirname(USER_VENDORS_PATH), { recursive: true });
  fs.writeFileSync(
    USER_VENDORS_PATH,
    JSON.stringify(
      {
        _comment:
          "Your personal-vendor exclusions for BUSINESS bill searches. personalVendors adds entries; suppressed turns off entries shipped with the plugin. Case-insensitive substring match against sender name AND email. Kept outside the plugin so upgrades keep it.",
        personalVendors: data.personalVendors,
        suppressed: data.suppressed,
      },
      null,
      2,
    ) + "\n",
  );
}

function normalizeEntries(entries: readonly string[]): string[] {
  return (entries ?? []).map((e) => String(e).trim()).filter((e) => e.length >= MIN_ENTRY_LENGTH);
}

/** Shipped list plus user additions, minus anything the user suppressed. */
export function loadPersonalVendors(): string[] {
  const user = readUserFile();
  const off = new Set(user.suppressed.map((v) => String(v).toLowerCase()));
  const seen = new Set<string>();
  const out: string[] = [];
  for (const v of [...readShippedVendors(), ...user.personalVendors]) {
    const entry = String(v).trim();
    if (entry.length < MIN_ENTRY_LENGTH) continue;
    const key = entry.toLowerCase();
    if (off.has(key) || seen.has(key)) continue;
    seen.add(key);
    out.push(entry);
  }
  return out;
}

export function listPersonalVendors() {
  const user = readUserFile();
  const active = loadPersonalVendors();
  return {
    active,
    shipped: readShippedVendors(),
    userAdded: user.personalVendors,
    suppressed: user.suppressed,
    configPath: USER_VENDORS_PATH,
    counts: { active: active.length, userAdded: user.personalVendors.length, suppressed: user.suppressed.length },
  };
}

export function addPersonalVendors(entries: readonly string[]) {
  const wanted = normalizeEntries(entries);
  const user = readUserFile();
  const shipped = new Set(readShippedVendors().map((v) => String(v).toLowerCase()));
  const have = new Set(user.personalVendors.map((v) => String(v).toLowerCase()));
  const added: string[] = [];
  const alreadyPresent: string[] = [];
  let changed = false;

  for (const entry of wanted) {
    const key = entry.toLowerCase();
    // Re-adding something previously suppressed should un-suppress it.
    if (user.suppressed.some((v) => String(v).toLowerCase() === key)) {
      user.suppressed = user.suppressed.filter((v) => String(v).toLowerCase() !== key);
      changed = true;
    }
    if (have.has(key) || shipped.has(key)) {
      alreadyPresent.push(entry);
      continue;
    }
    have.add(key);
    user.personalVendors.push(entry);
    added.push(entry);
    changed = true;
  }

  if (changed) writeUserFile(user);
  return { added, alreadyPresent, active: loadPersonalVendors(), configPath: USER_VENDORS_PATH };
}

export function removePersonalVendors(entries: readonly string[]) {
  const wanted = normalizeEntries(entries);
  const user = readUserFile();
  const shipped = readShippedVendors();
  const removed: string[] = [];
  const suppressed: string[] = [];
  const notFound: string[] = [];
  let changed = false;

  for (const entry of wanted) {
    const key = entry.toLowerCase();
    const inUser = user.personalVendors.some((v) => String(v).toLowerCase() === key);
    const inShipped = shipped.some((v) => String(v).toLowerCase() === key);

    if (inUser) {
      user.personalVendors = user.personalVendors.filter((v) => String(v).toLowerCase() !== key);
      removed.push(entry);
      changed = true;
    }
    if (inShipped) {
      if (!user.suppressed.some((v) => String(v).toLowerCase() === key)) {
        user.suppressed.push(entry);
        changed = true;
      }
      suppressed.push(entry);
    }
    if (!inUser && !inShipped) notFound.push(entry);
  }

  if (changed) writeUserFile(user);
  return { removed, suppressed, notFound, active: loadPersonalVendors(), configPath: USER_VENDORS_PATH };
}

/**
 * Literal, case-insensitive substring match against a sender's display name
 * OR email address. Returns the matched vendor-list entry, or null.
 */
export function matchPersonalVendor(sender: BillSender, vendors: string[]): string | null {
  const name = sender.name.toLowerCase();
  const email = sender.email.toLowerCase();
  for (const entry of vendors) {
    const needle = entry.toLowerCase();
    if (name.includes(needle) || email.includes(needle)) return entry;
  }
  return null;
}
