import { useDagStore } from "../../store/dagStore";
import { ConfigWindow } from "./ConfigWindow";
import { InputWindow } from "./InputWindow";
import { OutputWindow } from "./OutputWindow";

export function NodeInspector() {
	const inspectorOpen = useDagStore((s) => s.inspectorOpen);
	const selectedNodeId = useDagStore((s) => s.selectedNodeId);
	const nodes = useDagStore((s) => s.nodes);
	const snapshots = useDagStore((s) => s.snapshots);
	const closeInspector = useDagStore((s) => s.closeInspector);
	const node = nodes.find((n) => n.id === selectedNodeId);
	const snapshot = selectedNodeId ? snapshots[selectedNodeId] : undefined;

	if (!inspectorOpen || !node) {
		return null;
	}

	return (
		<div className="inspector">
			<header className="inspector__head">
				<div>
					<span className={`pill pill--${node.data.category.toLowerCase()}`}>
						{node.data.category}
					</span>
					<h2>{node.data.label}</h2>
					{snapshot ? (
						<small>
							{snapshot.status} · {Math.round(snapshot.duration_ms || 0)} ms
						</small>
					) : null}
				</div>
				<button
					type="button"
					onClick={closeInspector}
					aria-label="Fermer l'inspecteur"
				>
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
