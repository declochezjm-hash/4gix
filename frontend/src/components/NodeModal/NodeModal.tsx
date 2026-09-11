import { useEffect } from "react";
import { nodeChrome } from "../../lib/n8nCatalog";
import { catalogEntryIcon, N8nIconBadge } from "../../lib/n8nIcons";
import { useDagStore } from "../../store/dagStore";
import { ConfigWindow } from "./ConfigWindow";
import { InputWindow } from "./InputWindow";
import { OutputWindow } from "./OutputWindow";

export function NodeModal() {
	const inspectorOpen = useDagStore((s) => s.inspectorOpen);
	const selectedNodeId = useDagStore((s) => s.selectedNodeId);
	const nodes = useDagStore((s) => s.nodes);
	const snapshots = useDagStore((s) => s.snapshots);
	const closeInspector = useDagStore((s) => s.closeInspector);
	const runSelectedNode = useDagStore((s) => s.runSelectedNode);
	const running = useDagStore((s) => s.running);
	const node = nodes.find((n) => n.id === selectedNodeId);
	const snapshot = selectedNodeId ? snapshots[selectedNodeId] : undefined;

	useEffect(() => {
		if (!inspectorOpen) return;
		const onKey = (event: KeyboardEvent) => {
			if (event.key === "Escape") closeInspector();
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [inspectorOpen, closeInspector]);

	if (!inspectorOpen || !node) {
		return null;
	}

	const chrome = nodeChrome({
		nodeType: node.data.nodeType,
		category: node.data.category,
	});

	return (
		<div className="n8n-modal" role="dialog" aria-modal="true">
			<header className="n8n-modal__head">
				<div className="n8n-modal__identity">
					<N8nIconBadge
						icon={catalogEntryIcon({
							node_type: node.data.nodeType,
							category: node.data.category,
						})}
						color={chrome.color}
						size={18}
						className="n8n-modal__icon"
					/>
					<div>
						<p className="n8n-panel__kicker">{node.data.category}</p>
						<h2>{node.data.label}</h2>
						<small>
							{snapshot
								? `${snapshot.status} · ${Math.round(snapshot.duration_ms || 0)} ms`
								: node.data.nodeType}
						</small>
					</div>
				</div>
				<div className="n8n-modal__actions">
					<button
						type="button"
						className="n8n-test-btn"
						onClick={() => void runSelectedNode()}
						disabled={running}
					>
						{running ? "Executing…" : "Test step"}
					</button>
					<button
						type="button"
						className="n8n-icon-btn"
						onClick={closeInspector}
						aria-label="Fermer"
					>
						×
					</button>
				</div>
			</header>
			<div className="n8n-modal__cols">
				<InputWindow />
				<ConfigWindow />
				<OutputWindow />
			</div>
		</div>
	);
}
