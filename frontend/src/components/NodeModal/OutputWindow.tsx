import { MapViewer } from "../MapViewer/MapViewer";
import { useDagStore } from "../../store/dagStore";

function isFeatureCollection(value: unknown): value is { type: string; features: unknown[] } {
  return Boolean(value && typeof value === "object" && (value as { type?: string }).type === "FeatureCollection");
}

export function OutputWindow() {
  const selectedNodeId = useDagStore((s) => s.selectedNodeId);
  const snapshots = useDagStore((s) => s.snapshots);
  const snapshot = selectedNodeId ? snapshots[selectedNodeId] : undefined;

  return (
    <section className="inspector-pane">
      <header>
        <h3>Output</h3>
        <p>Snapshot Recflow après exécution</p>
      </header>
      {!snapshot ? (
        <div className="empty">Aucun snapshot. Exécutez le graphe pour inspecter la sortie.</div>
      ) : (
        <>
          <dl className="meta-grid">
            <div>
              <dt>Statut</dt>
              <dd className={snapshot.status}>{snapshot.status}</dd>
            </div>
            <div>
              <dt>Durée</dt>
              <dd>{snapshot.duration_ms} ms</dd>
            </div>
            {Object.entries(snapshot.metadata || {}).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
              </div>
            ))}
          </dl>
          {snapshot.error ? <p className="error-line">{snapshot.error}</p> : null}
          {isFeatureCollection(snapshot.preview) ? (
            <div className="map-embed">
              <MapViewer geojson={snapshot.preview} />
            </div>
          ) : null}
          <pre>{JSON.stringify(snapshot.preview, null, 2)}</pre>
        </>
      )}
    </section>
  );
}
