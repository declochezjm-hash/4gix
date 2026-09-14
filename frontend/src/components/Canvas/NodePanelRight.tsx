import { useEffect, useMemo, useRef, useState } from "react";
import { matchesNodeSearch } from "../../config/nodeRegistry";
import { groupCatalog, type N8nGroupId } from "../../lib/n8nCatalog";
import { ArrowLeft, Search } from "../../lib/n8nIcons";
import { useDagStore } from "../../store/dagStore";
import { NodePanelCategoryAccordion } from "./NodePanelCategoryAccordion";
import { NodePanelGroupDrilldown } from "./NodePanelGroupDrilldown";

const DRILL_DOWN_GROUPS: N8nGroupId[] = ["hitl"];

function isGroupExpanded(
	groupId: N8nGroupId,
	nodeCount: number,
	searching: boolean,
	userExpanded: readonly N8nGroupId[],
): boolean {
	if (nodeCount === 0) return false;
	if (searching) return true;
	return userExpanded.includes(groupId);
}

export function NodePanelRight() {
	const open = useDagStore((s) => s.nodePanelOpen);
	const nodePanelEpoch = useDagStore((s) => s.nodePanelEpoch);
	const userExpanded = useDagStore((s) => s.nodePanelExpandedGroups);
	const toggleNodePanelGroup = useDagStore((s) => s.toggleNodePanelGroup);
	const closeNodePanel = useDagStore((s) => s.closeNodePanel);
	const catalog = useDagStore((s) => s.catalog);
	const insertNodeFromPanel = useDagStore((s) => s.insertNodeFromPanel);
	const loadCatalog = useDagStore((s) => s.loadCatalog);
	const catalogLoaded = useDagStore((s) => s.catalogLoaded);
	const panelError = useDagStore((s) => s.error);
	const pendingConnect = useDagStore((s) => s.pendingConnect);
	const pendingEdgeInsert = useDagStore((s) => s.pendingEdgeInsert);
	const [query, setQuery] = useState("");
	const [drillGroupId, setDrillGroupId] = useState<N8nGroupId | null>(null);
	const searchRef = useRef<HTMLInputElement | null>(null);
	const panelOpenedAtRef = useRef(0);

	useEffect(() => {
		if (!open) {
			setQuery("");
			setDrillGroupId(null);
			return;
		}
		panelOpenedAtRef.current = performance.now();
		setQuery("");
		setDrillGroupId(null);
		void loadCatalog();
		const timer = window.setTimeout(() => searchRef.current?.focus(), 40);
		return () => window.clearTimeout(timer);
	}, [open, nodePanelEpoch, loadCatalog]);

	const handleToggleGroup = (groupId: N8nGroupId) => {
		if (performance.now() - panelOpenedAtRef.current < 400) return;
		toggleNodePanelGroup(groupId);
	};

	useEffect(() => {
		if (!open) return;
		const onKey = (event: KeyboardEvent) => {
			if (event.key !== "Escape") return;
			if (drillGroupId) {
				setDrillGroupId(null);
				return;
			}
			closeNodePanel();
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [open, closeNodePanel, drillGroupId]);

	const searching = query.trim().length > 0;

	const grouped = useMemo(() => {
		const filtered = searching
			? catalog.filter((entry) => matchesNodeSearch(entry, query))
			: catalog;
		return groupCatalog(filtered);
	}, [catalog, query, searching]);

	if (!open) return null;

	const drilled = drillGroupId
		? groupCatalog(catalog).find((g) => g.group.id === drillGroupId)
		: null;

	if (drillGroupId && drilled) {
		return (
			<aside className="n8n-panel" aria-label="Human in the loop">
				<NodePanelGroupDrilldown
					groupId={drillGroupId}
					nodes={drilled.nodes}
					onBack={() => setDrillGroupId(null)}
					onSelectNode={insertNodeFromPanel}
				/>
			</aside>
		);
	}

	return (
		<aside
			key={nodePanelEpoch}
			className="n8n-panel"
			aria-label="Ajouter un nœud"
		>
			<header className="n8n-panel__head">
				<div>
					<p className="n8n-panel__kicker">
						{pendingEdgeInsert
							? "Insérer sur la liaison"
							: pendingConnect
								? "Connecter un nœud"
								: "Ajouter un nœud"}
					</p>
					<h2>What happens next?</h2>
					<p className="n8n-panel__hint">
						Cliquez une catégorie pour l’ouvrir ou la fermer.
					</p>
				</div>
				<button
					type="button"
					className="n8n-icon-btn n8n-icon-btn--lucide"
					onClick={closeNodePanel}
					aria-label="Fermer le panneau"
				>
					<ArrowLeft size={20} strokeWidth={2} aria-hidden />
				</button>
			</header>
			<div className="n8n-panel__search">
				<Search
					size={16}
					strokeWidth={2}
					className="n8n-panel__search-icon"
					aria-hidden
				/>
				<input
					ref={searchRef}
					value={query}
					onChange={(event) => setQuery(event.target.value)}
					placeholder="Search nodes..."
					aria-label="Search nodes"
				/>
			</div>
			{catalogLoaded && catalog.length === 0 ? (
				<div className="n8n-panel__empty n8n-panel__empty--block">
					<p>
						{panelError ||
							"Impossible de charger les nœuds. Vérifiez que l’API tourne sur le port 8000."}
					</p>
					<button
						type="button"
						className="ghost-btn"
						onClick={() => void loadCatalog()}
					>
						Réessayer
					</button>
				</div>
			) : null}
			<div className="n8n-panel__list n8n-panel__list--accordion">
				{grouped.map(({ group, nodes }) => {
					if (searching && nodes.length === 0) return null;
					const expanded = isGroupExpanded(
						group.id,
						nodes.length,
						searching,
						userExpanded,
					);
					return (
						<NodePanelCategoryAccordion
							key={group.id}
							group={group}
							nodes={nodes}
							expanded={expanded}
							onToggle={() => handleToggleGroup(group.id)}
							onSelectNode={insertNodeFromPanel}
							defaultOpenSubgroups={searching}
							navigateOnClick={DRILL_DOWN_GROUPS.includes(group.id)}
							onNavigate={() => setDrillGroupId(group.id)}
						/>
					);
				})}
				{searching && !grouped.some(({ nodes }) => nodes.length > 0) ? (
					<p className="n8n-panel__empty">
						Aucun nœud ne correspond à la recherche.
					</p>
				) : null}
			</div>
		</aside>
	);
}
