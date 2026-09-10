import { useEffect } from "react";
import { FlowCanvas } from "./components/Canvas/FlowCanvas";
import { NodePalette } from "./components/Canvas/NodePalette";
import { NodeInspector } from "./components/NodeModal/NodeInspector";
import { useDagStore } from "./store/dagStore";

export default function App() {
  const loadCatalog = useDagStore((s) => s.loadCatalog);
  const runDag = useDagStore((s) => s.runDag);
  const running = useDagStore((s) => s.running);
  const error = useDagStore((s) => s.error);
  const lastExecution = useDagStore((s) => s.lastExecution);
  const nodes = useDagStore((s) => s.nodes);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="logo">4GIx</span>
          <div>
            <strong>Recflow Canvas</strong>
            <small>ETL / ELT géospatial — moteur DAG local</small>
          </div>
        </div>
        <div className="topbar__actions">
          {lastExecution ? (
            <span className={`status status--${lastExecution.status}`}>
              {lastExecution.status} · {lastExecution.duration_ms} ms · {lastExecution.node_count} nœuds
            </span>
          ) : (
            <span className="status">{nodes.length} nœud(s) sur le canvas</span>
          )}
          {error ? <span className="status status--error">{error}</span> : null}
          <button type="button" className="run-btn" onClick={() => void runDag()} disabled={running || nodes.length === 0}>
            {running ? "Exécution…" : "Exécuter le DAG"}
          </button>
        </div>
      </header>
      <div className="workspace">
        <NodePalette />
        <main className="workspace__main">
          <FlowCanvas />
          <NodeInspector />
        </main>
      </div>
    </div>
  );
}
