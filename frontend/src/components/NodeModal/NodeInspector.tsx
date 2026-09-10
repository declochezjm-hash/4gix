import { ConfigWindow } from "./ConfigWindow";
import { InputWindow } from "./InputWindow";
import { OutputWindow } from "./OutputWindow";
import { useDagStore } from "../../store/dagStore";

export function NodeInspector() {
  const inspectorOpen = useDagStore((s) => s.inspectorOpen);
  const selectedNodeId = useDagStore((s) => s.selectedNodeId);
  const nodes = useDagStore((s) => s.nodes);
  const closeInspector = useDagStore((s) => s.closeInspector);
  const node = nodes.find((n) => n.id === selectedNodeId);

  if (!inspectorOpen || !node) {
    return null;
  }

  return (
    <div className="inspector">
      <header className="inspector__head">
        <div>
          <span className={`pill pill--${node.data.category.toLowerCase()}`}>{node.data.category}</span>
          <h2>{node.data.label}</h2>
        </div>
        <button type="button" onClick={closeInspector} aria-label="Fermer l'inspecteur">
          ×
        </button>
      </header>
      <div className="inspector__grid">
        <InputWindow />
        <ConfigWindow />
        <OutputWindow />
      </div>
    </div>
  );
}
