import { useEffect } from "react";
import { FlowCanvas } from "./components/Canvas/FlowCanvas";
import { NodePalette } from "./components/Canvas/NodePalette";
import { NodeInspector } from "./components/NodeModal/NodeInspector";
import { useDagStore } from "./store/dagStore";

export default function App() {
	const loadCatalog = useDagStore((s) => s.loadCatalog);
	const loadWorkflows = useDagStore((s) => s.loadWorkflows);
	const loadWorkflow = useDagStore((s) => s.loadWorkflow);
	const saveCurrentWorkflow = useDagStore((s) => s.saveCurrentWorkflow);
	const runDag = useDagStore((s) => s.runDag);
	const running = useDagStore((s) => s.running);
	const error = useDagStore((s) => s.error);
	const lastExecution = useDagStore((s) => s.lastExecution);
	const nodes = useDagStore((s) => s.nodes);
	const workflows = useDagStore((s) => s.workflows);
	const workflowId = useDagStore((s) => s.workflowId);
	const workflowName = useDagStore((s) => s.workflowName);
	const setWorkflowName = useDagStore((s) => s.setWorkflowName);

	useEffect(() => {
		void loadCatalog();
		void loadWorkflows();
	}, [loadCatalog, loadWorkflows]);

	return (
		<div className="app-shell">
			<header className="topbar">
				<div className="brand">
					<span className="logo">4GIx</span>
					<div>
						<strong>Recflow Canvas</strong>
						<small>ETL / ELT géospatial — inspecteur synchro Phase 2</small>
					</div>
				</div>
				<div className="topbar__actions">
					<input
						className="workflow-name"
						value={workflowName}
						onChange={(e) => setWorkflowName(e.target.value)}
						placeholder="Nom du workflow"
					/>
					<select
						value={workflowId || ""}
						onChange={(e) => {
							if (e.target.value) loadWorkflow(e.target.value);
						}}
					>
						<option value="">Charger…</option>
						{workflows.map((item) => (
							<option key={item.id} value={item.id}>
								{item.name}
							</option>
						))}
					</select>
					<button
						type="button"
						className="ghost-btn"
						onClick={() => void saveCurrentWorkflow()}
						disabled={nodes.length === 0}
					>
						Enregistrer
					</button>
					{lastExecution ? (
						<span
							className={`status status--${String(lastExecution.status).toLowerCase()}`}
						>
							{lastExecution.status} · {Math.round(lastExecution.duration_ms)}{" "}
							ms · {lastExecution.node_count} nœuds
						</span>
					) : (
						<span className="status">{nodes.length} nœud(s) sur le canvas</span>
					)}
					{error ? <span className="status status--error">{error}</span> : null}
					<button
						type="button"
						className="run-btn"
						onClick={() => void runDag()}
						disabled={running || nodes.length === 0}
					>
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
