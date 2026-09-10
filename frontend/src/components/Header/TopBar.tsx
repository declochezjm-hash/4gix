import { type ChangeEvent, useRef } from "react";
import { useDagStore } from "../../store/dagStore";

export function TopBar() {
	const loadWorkflow = useDagStore((s) => s.loadWorkflow);
	const saveCurrentWorkflow = useDagStore((s) => s.saveCurrentWorkflow);
	const importLocalWorkflowFile = useDagStore((s) => s.importLocalWorkflowFile);
	const exportCurrentFmw = useDagStore((s) => s.exportCurrentFmw);
	const runDag = useDagStore((s) => s.runDag);
	const openNodePanel = useDagStore((s) => s.openNodePanel);
	const running = useDagStore((s) => s.running);
	const error = useDagStore((s) => s.error);
	const importNotice = useDagStore((s) => s.importNotice);
	const lastExecution = useDagStore((s) => s.lastExecution);
	const nodes = useDagStore((s) => s.nodes);
	const workflows = useDagStore((s) => s.workflows);
	const workflowId = useDagStore((s) => s.workflowId);
	const workflowName = useDagStore((s) => s.workflowName);
	const setWorkflowName = useDagStore((s) => s.setWorkflowName);

	const fileInputRef = useRef<HTMLInputElement | null>(null);

	const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0];
		if (file) void importLocalWorkflowFile(file);
		event.target.value = "";
	};

	return (
		<header className="topbar">
			<div className="brand">
				<span className="logo">4GIx</span>
				<div>
					<strong>Recflow Canvas</strong>
					<small>ETL SIG natif · FME en lecture approximative (exécution sans FME)</small>
				</div>
			</div>
			<div className="topbar__actions">
				<input
					className="workflow-name"
					value={workflowName}
					onChange={(e) => setWorkflowName(e.target.value)}
					placeholder="Nom du workflow"
				/>

				<input
					type="file"
					id="fme-file-input"
					ref={fileInputRef}
					className="import-file-input"
					accept=".fmw,.fmwt,.json,.4gix.json,.zip"
					onChange={handleFileChange}
				/>

				<button
					type="button"
					id="btn-import-fmw-json"
					className="import-file-btn"
					onClick={() => fileInputRef.current?.click()}
					title="Importe .fmw, JSON workflow ou .zip Shapefile — exécution 4GIx"
				>
					<svg
						className="import-file-btn__icon"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
						aria-hidden
					>
						<path
							strokeLinecap="round"
							strokeLinejoin="round"
							strokeWidth="2"
							d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
						/>
					</svg>
					Importer (.fmw / .json / .zip)
				</button>

				<select
					value={workflowId || ""}
					onChange={(e) => {
						if (e.target.value) loadWorkflow(e.target.value);
					}}
					aria-label="Charger un workflow enregistré"
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
					onClick={() => void exportCurrentFmw()}
					disabled={nodes.length === 0}
				>
					Export FME (.fmw)
				</button>
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
						{lastExecution.status} · {Math.round(lastExecution.duration_ms)} ms ·{" "}
						{lastExecution.node_count} nœuds
					</span>
				) : (
					<span className="status">{nodes.length} nœud(s)</span>
				)}
				{error ? <span className="status status--error">{error}</span> : null}
				{importNotice ? (
					<span className="status status--completed">{importNotice}</span>
				) : null}
				<button
					type="button"
					className="canvas-plus canvas-plus--bar"
					aria-label="Ajouter un nœud"
					onClick={() => openNodePanel(null)}
				>
					+
				</button>
				<button
					type="button"
					className="run-btn"
					onClick={() => void runDag()}
					disabled={running || nodes.length === 0}
					title="Exécute le graphe avec le moteur ETL 4GIx (PostGIS, transformers FME-like)"
				>
					{running ? "Exécution…" : "Execute workflow (4GIx)"}
				</button>
			</div>
		</header>
	);
}
