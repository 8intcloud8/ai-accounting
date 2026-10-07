import type { McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import { useApp } from "@modelcontextprotocol/ext-apps/react";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BillTable } from "./components/BillTable";
import { SaveSummary } from "./components/SaveSummary";
import { ProgressState } from "./components/ProgressState";
import type { SaveBillsStructured, SearchBillsStructured } from "./types";
import styles from "./mcp-app.module.css";

const DEFAULT_ROOT_FOLDER = "~/Documents/Bills";

function isSearchResult(sc: unknown): sc is SearchBillsStructured {
  return !!sc && typeof sc === "object" && Array.isArray((sc as Record<string, unknown>).bills);
}

function isSaveResult(sc: unknown): sc is SaveBillsStructured {
  return (
    !!sc && typeof sc === "object" && typeof (sc as Record<string, unknown>).savedCount === "number"
  );
}

// This app has no Gmail access of its own (sandboxed iframe) — only the
// agent can fetch Gmail data, using its own connected Gmail tools. So
// "Save selected" hands control back to the agent via sendMessage.
type Phase = "connecting" | "pending-save" | "results" | "saved";

function BillSearchApp() {
  const [hostContext, setHostContext] = useState<McpUiHostContext | undefined>();
  const [phase, setPhase] = useState<Phase>("connecting");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [searchResult, setSearchResult] = useState<SearchBillsStructured | null>(null);
  const [saveResult, setSaveResult] = useState<SaveBillsStructured | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filterText, setFilterText] = useState("");
  const [rootFolder, setRootFolder] = useState(DEFAULT_ROOT_FOLDER);

  const applyToolResult = useCallback((result: CallToolResult) => {
    if (result.isError) {
      const text = result.content?.find((c) => c.type === "text")?.text;
      setErrorMessage(text ?? "Tool call failed.");
      setPhase("results");
      return;
    }
    const sc = result.structuredContent;
    if (isSearchResult(sc)) {
      setSearchResult(sc);
      setSelected(new Set(sc.bills.map((b) => b.threadId)));
      setErrorMessage(null);
      setPhase("results");
    } else if (isSaveResult(sc)) {
      setSaveResult(sc);
      setErrorMessage(null);
      setPhase("saved");
    }
  }, []);

  const { app, error } = useApp({
    appInfo: { name: "Bill Checklist", version: "1.0.0" },
    capabilities: {},
    onAppCreated: (app) => {
      app.ontoolresult = async (result) => {
        applyToolResult(result);
      };

      app.onerror = (err) => {
        setErrorMessage(String(err));
      };

      app.onhostcontextchanged = (params) => {
        setHostContext((prev) => ({ ...prev, ...params }));
      };
    },
  });

  useEffect(() => {
    if (app) setHostContext(app.getHostContext());
  }, [app]);

  const requestSave = useCallback(async () => {
    if (!app || !searchResult) return;
    setErrorMessage(null);
    setPhase("pending-save");
    try {
      const ids = Array.from(selected).join(", ");
      const { isError } = await app.sendMessage({
        role: "user",
        content: [
          {
            type: "text",
            text:
              `Save these ${selected.size} bill(s) to root folder "${rootFolder}" ` +
              `(category: ${searchResult.category}, date range: ${searchResult.dateRangeTag}). ` +
              `Thread ids: ${ids}`,
          },
        ],
      });
      if (isError) {
        setErrorMessage("The request wasn't accepted.");
        setPhase("results");
      }
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : String(e));
      setPhase("results");
    }
  }, [app, searchResult, selected, rootFolder]);

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback((ids: string[], checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (checked) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }, []);

  const openLink = useCallback((url: string) => void app?.openLink({ url }), [app]);

  if (error) {
    return (
      <div className={styles.app}>
        <p className={styles.errorText}>ERROR: {error.message}</p>
      </div>
    );
  }
  if (!app) {
    return <ProgressState label="Connecting…" />;
  }

  const busy = phase === "pending-save";

  return (
    <main
      className={styles.app}
      style={{
        paddingTop: hostContext?.safeAreaInsets?.top,
        paddingRight: hostContext?.safeAreaInsets?.right,
        paddingBottom: hostContext?.safeAreaInsets?.bottom,
        paddingLeft: hostContext?.safeAreaInsets?.left,
      }}
    >
      <div className={styles.header}>
        <h2>Bill Checklist</h2>
        <p className={styles.subtitle}>Multi-pass Gmail search for bills, invoices, and receipts.</p>
      </div>

      {searchResult && (
        <p className={styles.searchScope}>
          {searchResult.category === "bills" ? "Bills" : searchResult.category === "business" ? "Business" : "Personal"}
          {" · "}{searchResult.dateFrom} to {searchResult.dateTo}
        </p>
      )}

      {errorMessage && <p className={styles.errorText}>{errorMessage}</p>}

      {phase === "connecting" && !searchResult && <ProgressState label="Waiting for search results…" />}

      {searchResult && phase !== "connecting" && phase !== "saved" && (
        <>
          {searchResult.category === "business" && searchResult.excluded.length > 0 && (
            <p className={styles.excludedNote}>
              Excluded {searchResult.excluded.length} personal-vendor result(s):{" "}
              {searchResult.excluded.map((e) => `${e.vendor} (matched "${e.matchedRule}")`).join(", ")}
            </p>
          )}

          <BillTable
            bills={searchResult.bills}
            selected={selected}
            onToggle={toggle}
            onToggleAll={toggleAll}
            filterText={filterText}
            onFilterChange={setFilterText}
            onOpenLink={openLink}
          />

          <div className={styles.rootFolderRow}>
            <label htmlFor="root_folder">Bills root folder:</label>
            <input
              id="root_folder"
              type="text"
              value={rootFolder}
              onChange={(e) => setRootFolder(e.target.value)}
            />
          </div>

          <div className={styles.toolbar}>
            <button
              type="button"
              className={styles.button}
              disabled={selected.size === 0 || busy}
              onClick={requestSave}
            >
              {phase === "pending-save" ? "Saving…" : `Save selected (${selected.size})`}
            </button>
          </div>

          {phase === "pending-save" && <ProgressState label="Saving the selected bills…" />}
        </>
      )}

      {phase === "saved" && saveResult && <SaveSummary result={saveResult} onBack={() => setPhase("results")} />}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BillSearchApp />
  </StrictMode>,
);
