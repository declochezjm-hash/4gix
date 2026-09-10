import { useDagStore } from "../../store/dagStore";

export function InputWindow() {
  const selectedNodeId = useDagStore((s) => s.selectedNodeId);
  const nodes = useDagStore((s) => s.nodes);
  const edges = useDagStore((s) => s.edges);
  const snapshots = useDagStore((s) => s.snapshots);

  const parents = edges
    .filter((edge) => edge.target === selectedNodeId)
    .map((edge) => nodes.find((n) => n.id === edge.source))
    .filter(Boolean);

  return (
    <section className="inspector-pane">
      <header>
        <h3>Input</h3>
        <p>Données issues des nœuds parents</p>
      </header>
      {parents.length === 0 ? (
        <div className="empty">Aucun parent connecté. Reliez un Reader ou Transformer en amont.</div>
      ) : (
        parents.map((parent) => {
          const snap = parent ? snapshots[parent.id] : undefined;
          return (
            <article key={parent!.id} className="snapshot-card">
              <h4>{parent!.data.label}</h4>
              <p className="muted">{parent!.data.nodeType}</p>
              {snap ? (
                <pre>{JSON.stringify(snap.preview ?? snap.metadata, null, 2)}</pre>
              ) : (
                <p className="muted">Pas encore de snapshot — lancez le DAG.</p>
              )}
            </article>
          );
        })
      )}
    </section>
  );
}
