import type { Browser } from "puppeteer";
import fs from "node:fs";

let browserPromise: Promise<Browser> | null = null;

async function getBrowser(): Promise<Browser> {
  if (browserPromise) {
    const pending = browserPromise;
    const browser = await pending;
    if (browser.connected) return browser;
    if (browserPromise === pending) browserPromise = null;
  }
  if (!browserPromise) {
    // Lazy import: the server (and its interactive UI) must load even when
    // puppeteer isn't installed. Only PDF rendering needs it.
    const pending = import("puppeteer")
      .then(async (m) => {
        const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
        const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH ||
          (process.platform === "darwin" && fs.existsSync(macChrome) ? macChrome : undefined);
        const browser = await m.default.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
        browser.once("disconnected", () => {
          if (browserPromise === pending) browserPromise = null;
        });
        return browser;
      })
      .catch((e) => {
        if (browserPromise === pending) browserPromise = null;
        throw new Error(
          "Could not start the invoice PDF browser: " +
            (e instanceof Error ? e.message : String(e))
        );
      });
    browserPromise = pending;
  }
  return browserPromise;
}

export async function renderHtmlToPdf(html: string, outPath: string): Promise<void> {
  const browser = await getBrowser();
  let page: Awaited<ReturnType<Browser["newPage"]>> | undefined;
  try {
    page = await browser.newPage();
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
  } catch (error) {
    // A closed protocol connection can precede the disconnected event. Evict
    // this browser so the caller's retry starts a fresh transport.
    if (!browser.connected || /connection closed|target closed|session closed|browser.*disconnect/i.test(String(error))) {
      const pending = browserPromise;
      if (pending && await pending.catch(() => null) === browser && browserPromise === pending) {
        browserPromise = null;
      }
      await browser.close().catch(() => {});
    }
    throw error;
  } finally {
    // Cleanup must not hide the rendering error when the browser disconnected.
    await page?.close().catch(() => {});
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
    const pending = browserPromise;
    browserPromise = null;
    const browser = await pending;
    await browser.close();
  }
}
