import type { Node } from "@xyflow/react";
import {
	LayoutList,
	MoreVertical,
	Search,
	SlidersHorizontal,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { FlowNodeData, WorkflowRecord } from "../../lib/api";
import { topologicalLayerMap } from "../../lib/workflowPagination";
import { useDagStore } from "../../store/dagStore";

type OverviewTab = "nodes" | "workflows";

const PAGE_SIZES = [25, 50, 100] as const;

function formatRelative(iso?: string): string {
	if (!iso) return "—";
	const date = new Date(iso);
	if (Number.isNaN(date.getTime())) return "—";
	const diff = Date.now() - date.getTime();
	const minutes = Math.floor(diff / 60000);
	if (minutes < 60) return `${minutes} min`;
	const hours = Math.floor(minutes / 60);
	if (hours < 48) return `${hours} h`;
	const days = Math.floor(hours / 24);
	if (days < 60) return `${days} j`;
	return date.toLocaleDateString("fr-FR");
}

function formatCreated(iso?: string): string {
	if (!iso) return "—";
	const date = new Date(iso);
	if (Number.isNaN(date.getTime())) return "—";
	return date.toLocaleDateString("fr-FR", {
		day: "numeric",
		month: "long",
		year: "numeric",
	});
}

function nodeRowMeta(node: Node<FlowNodeData>, layer: number) {
	return {
		id: node.id,
		label: node.data.label || node.id,
		type: node.data.nodeType,
		category: node.data.category,
		layer,
		disabled: Boolean(node.data.disabled),
		status: node.data.status || "idle",
	};
}

export function ProjectOverview() {
	const nodes = useDagStore((s) => s.nodes);
	const edges = useDagStore((s) => s.edges);
	const workflows = useDagStore((s) => s.workflows);
	const workflowId = useDagStore((s) => s.workflowId);
	const workflowName = useDagStore((s) => s.workflowName);
	const loadWorkflow = useDagStore((s) => s.loadWorkflow);
	const loadWorkflows = useDagStore((s) => s.loadWorkflows);
	const focusNodeOnCanvas = useDagStore((s) => s.focusNodeOnCanvas);
	const openInspector = useDagStore((s) => s.openInspector);
	const setAppView = useDagStore((s) => s.setAppView);
	const newWorkflow = useDagStore((s) => s.newWorkflow);
	const toggleNodeDisabled = useDagStore((s) => s.toggleNodeDisabled);
	const canvasPages = useDagStore((s) => s.canvasPages);

	const [tab, setTab] = useState<OverviewTab>("nodes");
	const [search, setSearch] = useState("");
	const [sort, setSort] = useState<"name" | "type" | "layer">("layer");
	const [page, setPage] = useState(0);
	const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[1]);
	const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

	const layers = useMemo(
		() => topologicalLayerMap(nodes, edges),
		[nodes, edges],
	);

	const nodeRows = useMemo(() => {
		const q = search.trim().toLowerCase();
		let rows = nodes.map((node) => nodeRowMeta(node, layers.get(node.id) ?? 0));
		if (q) {
			rows = rows.filter(
				(row) =>
					row.label.toLowerCase().includes(q) ||
					row.type.toLowerCase().includes(q) ||
					row.id.toLowerCase().includes(q),
			);
		}
		rows.sort((a, b) => {
			if (sort === "name") return a.label.localeCompare(b.label, "fr");
			if (sort === "type") return a.type.localeCompare(b.type, "fr");
			return a.layer - b.layer || a.label.localeCompare(b.label, "fr");
		});
		return rows;
	}, [nodes, layers, search, sort]);

	const workflowRows = useMemo(() => {
		const q = search.trim().toLowerCase();
		let rows = [...workflows];
		if (q) {
			rows = rows.filter(
				(w) =>
					w.name.toLowerCase().includes(q) || w.id.toLowerCase().includes(q),
			);
		}
		rows.sort((a, b) => {
			const ta = new Date(a.updated_at || a.created_at || 0).getTime();
			const tb = new Date(b.updated_at || b.created_at || 0).getTime();
			return tb - ta;
		});
		return rows;
	}, [workflows, search]);

	const activeList = tab === "nodes" ? nodeRows : workflowRows;
	const totalPages = Math.max(1, Math.ceil(activeList.length / pageSize));
	const safePage = Math.min(page, totalPages - 1);
	const sliceStart = safePage * pageSize;
	const pageItems = activeList.slice(sliceStart, sliceStart + pageSize);

	const openWorkflow = (record: WorkflowRecord) => {
		loadWorkflow(record.id);
		setAppView("editor");
	};

	const subtitle =
		tab === "nodes"
			? `Tous les nœuds du projet « ${workflowName} » (${nodes.length} nœuds, ${edges.length} liaisons, ${canvasPages.length} pages canvas).`
			: "Workflows enregistrés sur le serveur 4GIx — ouvrez, exécutez ou créez un nouveau graphe.";

	return (
		<div className="project-overview">
			<header className="project-overview__head">
				<div className="project-overview__head-copy">
					<h1>Vue d'ensemble</h1>
					<p className="project-overview__subtitle">{subtitle}</p>
				</div>
				<button
					type="button"
					className="run-btn project-overview__create"
					onClick={() => newWorkflow()}
				>
					Créer un workflow
				</button>
			</header>

			<div className="project-overview__tabs" role="tablist">
				<button
					type="button"
					role="tab"
					className={tab === "nodes" ? "is-active" : ""}
					onClick={() => {
						setTab("nodes");
						setPage(0);
					}}
				>
					Nœuds du projet
				</button>
				<button
					type="button"
					role="tab"
					className={tab === "workflows" ? "is-active" : ""}
					onClick={() => {
						setTab("workflows");
						setPage(0);
						void loadWorkflows();
					}}
				>
					Workflows
				</button>
				<button type="button" role="tab" className="is-disabled" disabled>
					Exécutions
				</button>
			</div>

			<div className="project-overview__toolbar">
				<div className="project-overview__search">
					<Search size={16} aria-hidden />
					<input
						type="search"
						placeholder="Rechercher"
						value={search}
						onChange={(e) => {
							setSearch(e.target.value);
							setPage(0);
						}}
					/>
				</div>
				<select
					className="project-overview__sort"
					value={tab === "nodes" ? sort : "updated"}
					onChange={(e) => {
						if (tab === "nodes") {
							setSort(e.target.value as "name" | "type" | "layer");
						}
					}}
					disabled={tab !== "nodes"}
					aria-label="Trier"
				>
					{tab === "nodes" ? (
						<>
							<option value="layer">Trier par étape du flux</option>
							<option value="name">Trier par nom</option>
							<option value="type">Trier par type</option>
						</>
					) : (
						<option value="updated">Trier par dernière mise à jour</option>
					)}
				</select>
				<button
					type="button"
					className="project-overview__icon-btn"
					title="Filtres (à venir)"
					disabled
				>
					<SlidersHorizontal size={18} />
				</button>
				<button
					type="button"
					className="project-overview__icon-btn is-active"
					title="Vue liste"
				>
					<LayoutList size={18} />
				</button>
			</div>

			<ul className="overview-cards">
				{pageItems.length === 0 ? (
					<li className="overview-cards__empty">
						{tab === "nodes"
							? "Aucun nœud — importez un .fmw ou passez par l'éditeur."
							: "Aucun workflow enregistré."}
					</li>
				) : null}

				{tab === "nodes"
					? (pageItems as ReturnType<typeof nodeRowMeta>[]).map((row) => {
							const active = !row.disabled;
							return (
								<li key={row.id} className="overview-card">
									<button
										type="button"
										className="overview-card__main"
										onClick={() => focusNodeOnCanvas(row.id)}
									>
										<strong>{row.label}</strong>
										<span className="overview-card__meta">
											{row.type} · étape {row.layer + 1} · {row.category}
										</span>
									</button>
									<div className="overview-card__aside">
										<span className="overview-tag">
											<span className="overview-tag__dot" aria-hidden />
											{row.category || "Nœud"}
										</span>
										<label
											className="overview-switch"
											onClick={(e) => e.stopPropagation()}
											onKeyDown={(e) => e.stopPropagation()}
										>
											<span
												className={
													active
														? "overview-switch__label is-on"
														: "overview-switch__label"
												}
											>
												{active ? "Actif" : "Inactif"}
											</span>
											<input
												type="checkbox"
												checked={active}
												onChange={() => toggleNodeDisabled(row.id)}
												aria-label={`Activer ${row.label}`}
											/>
											<span className="overview-switch__track" aria-hidden />
										</label>
										<div className="overview-card__menu-wrap">
											<button
												type="button"
												className="overview-card__menu-btn"
												aria-label="Actions"
												onClick={() =>
													setMenuOpenId(menuOpenId === row.id ? null : row.id)
												}
											>
												<MoreVertical size={18} />
											</button>
											{menuOpenId === row.id ? (
												<div className="overview-card__menu" role="menu">
													<button
														type="button"
														role="menuitem"
														onClick={() => {
															focusNodeOnCanvas(row.id);
															setMenuOpenId(null);
														}}
													>
														Ouvrir sur le canvas
													</button>
													<button
														type="button"
														role="menuitem"
														onClick={() => {
															openInspector(row.id);
															setAppView("editor");
															setMenuOpenId(null);
														}}
													>
														Inspecter
													</button>
													<button
														type="button"
														role="menuitem"
														onClick={() => {
															toggleNodeDisabled(row.id);
															setMenuOpenId(null);
														}}
													>
														{active ? "Désactiver" : "Activer"}
													</button>
												</div>
											) : null}
										</div>
									</div>
								</li>
							);
						})
					: (pageItems as WorkflowRecord[]).map((record) => {
							const count =
								(record.definition?.nodes as unknown[] | undefined)?.length ??
								0;
							const isCurrent = record.id === workflowId;
							const updated = formatRelative(
								record.updated_at || record.created_at,
							);
							const created = formatCreated(record.created_at);
							return (
								<li key={record.id} className="overview-card">
									<button
										type="button"
										className="overview-card__main"
										onClick={() => openWorkflow(record)}
									>
										<strong>{record.name}</strong>
										<span className="overview-card__meta">
											Dernière mise à jour {updated} | Créé {created} · {count}{" "}
											nœud(s)
										</span>
									</button>
									<div className="overview-card__aside">
										<span className="overview-tag">
											<span className="overview-tag__dot" aria-hidden />
											Projet
										</span>
										<label
											className="overview-switch"
											onClick={(e) => e.stopPropagation()}
											onKeyDown={(e) => e.stopPropagation()}
										>
											<span
												className={
													isCurrent
														? "overview-switch__label is-on"
														: "overview-switch__label"
												}
											>
												{isCurrent ? "Ouvert" : "Fermé"}
											</span>
											<input
												type="checkbox"
												checked={isCurrent}
												onChange={(e) => {
													if (e.target.checked) {
														openWorkflow(record);
														return;
													}
													if (isCurrent) {
														newWorkflow();
													}
												}}
												aria-label={
													isCurrent
														? `Fermer ${record.name}`
														: `Ouvrir ${record.name}`
												}
											/>
											<span className="overview-switch__track" aria-hidden />
										</label>
										<div className="overview-card__menu-wrap">
											<button
												type="button"
												className="overview-card__menu-btn"
												aria-label="Actions"
												onClick={() =>
													setMenuOpenId(
														menuOpenId === record.id ? null : record.id,
													)
												}
											>
												<MoreVertical size={18} />
											</button>
											{menuOpenId === record.id ? (
												<div className="overview-card__menu" role="menu">
													<button
														type="button"
														role="menuitem"
														onClick={() => {
															openWorkflow(record);
															setMenuOpenId(null);
														}}
													>
														Ouvrir dans l'éditeur
													</button>
													<button
														type="button"
														role="menuitem"
														onClick={() => {
															setAppView("editor");
															setMenuOpenId(null);
														}}
													>
														Aller au canvas
													</button>
												</div>
											) : null}
										</div>
									</div>
								</li>
							);
						})}
			</ul>

			<footer className="project-overview__footer">
				<div className="project-overview__pager">
					<span className="project-overview__total">
						Total {activeList.length}
					</span>
					<div className="project-overview__page-nums">
						{Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
							let pageNum = i;
							if (totalPages > 7) {
								const start = Math.max(
									0,
									Math.min(safePage - 3, totalPages - 7),
								);
								pageNum = start + i;
							}
							return (
								<button
									key={pageNum}
									type="button"
									className={
										pageNum === safePage
											? "project-overview__page-btn is-current"
											: "project-overview__page-btn"
									}
									onClick={() => setPage(pageNum)}
								>
									{pageNum + 1}
								</button>
							);
						})}
					</div>
					<select
						className="project-overview__page-size"
						value={pageSize}
						onChange={(e) => {
							setPageSize(Number(e.target.value));
							setPage(0);
						}}
						aria-label="Éléments par page"
					>
						{PAGE_SIZES.map((size) => (
							<option key={size} value={size}>
								{size}/page
							</option>
						))}
					</select>
				</div>
			</footer>
		</div>
	);
}
