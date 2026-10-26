import type { Browser } from "puppeteer";
import fs from "node:fs";

let browserPromise: Promise<Browser> | null = null;

async function getBrowser(): Promise<Browser> {
  if (!browserPromise) {
    // Lazy import: the server (and its interactive UI) must load even when
    // puppeteer isn't installed. Only PDF rendering needs it.
    browserPromise = import("puppeteer")
      .then((m) => {
        const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
        const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH ||
          (process.platform === "darwin" && fs.existsSync(macChrome) ? macChrome : undefined);
        return m.default.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
      })
      .catch((e) => {
        browserPromise = null;
        throw new Error(
          "PDF rendering needs puppeteer, which isn't available: " +
            (e instanceof Error ? e.message : String(e))
        );
      });
  }
  return browserPromise;
}

export async function renderHtmlToPdf(html: string, outPath: string): Promise<void> {
  const browser = await getBrowser();
  const page = await browser.newPage();
  try {
    // Email bodies are attacker-controlled HTML. Disabling JS blocks any
    // <script>/fetch()-driven requests (SSRF-adjacent risk) while still
    // letting normal <img>/<link> resources load for a faithful render.
    await page.setJavaScriptEnabled(false);
    // setContent only supports load/domcontentloaded (not networkidle*) —
    // "load" fires once all referenced resources (images, etc.) finish.
    await page.setContent(html, { waitUntil: "load", timeout: 15_000 });
    await page.pdf({
      path: outPath as `${string}.pdf`,
      format: "A4",
      printBackground: true,
      margin: { top: "12mm", bottom: "12mm", left: "12mm", right: "12mm" },
    });
  } finally {
    await page.close();
  }
}

export function wrapPlainTextAsHtml(text: string, subject: string): string {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${subject}</title></head><body><pre style="font-family: sans-serif; white-space: pre-wrap; font-size: 12px;">${escaped}</pre></body></html>`;
}

/** Call once at process shutdown to release the shared headless browser. */
export async function closePdfBrowser(): Promise<void> {
  if (browserPromise) {
    const browser = await browserPromise;
    await browser.close();
    browserPromise = null;
  }
}
