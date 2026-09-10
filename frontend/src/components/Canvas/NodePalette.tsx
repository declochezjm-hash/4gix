import { useDagStore } from "../../store/dagStore";

export function NodePalette() {
  const catalog = useDagStore((s) => s.catalog);
  const addCatalogNode = useDagStore((s) => s.addCatalogNode);
  const categories = ["Reader", "Transformer", "Writer"] as const;

  return (
    <aside className="palette">
      <header>
        <h2>Nœuds</h2>
        <p>Glissez un type sur le canvas, ou cliquez pour l'ajouter.</p>
      </header>
      {categories.map((category) => (
        <section key={category}>
          <h3>{category}s</h3>
          <ul>
            {catalog
              .filter((n) => n.category === category)
              .map((entry) => (
                <li key={entry.node_type}>
                  <button
                    type="button"
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData("application/4gix-node", JSON.stringify(entry));
                      event.dataTransfer.effectAllowed = "move";
                    }}
                    onClick={() => addCatalogNode(entry)}
                  >
                    <span>{entry.label}</span>
                    {entry.is_spatial ? <em>SIG</em> : null}
                  </button>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}
