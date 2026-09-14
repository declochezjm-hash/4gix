import { useEffect, useMemo, useRef, useState } from "react";
import type { CatalogNode } from "../../lib/api";
import { accentForNode } from "../../lib/connectorBrands";
import { matchesNodeSearch } from "../../config/nodeRegistry";
import {
	catalogSubgroups,
	groupMeta,
	type N8nGroupId,
} from "../../lib/n8nCatalog";
import {
	ArrowLeft,
	ChevronDown,
	Search,
	groupLucideIcon,
} from "../../lib/n8nIcons";
import { NodePanelEntry } from "./NodePanelEntry";

type NodePanelGroupDrilldownProps = {
	groupId: N8nGroupId;
	nodes: CatalogNode[];
	onBack: () => void;
	onSelectNode: (entry: CatalogNode) => void;
};

export function NodePanelGroupDrilldown({
	groupId,
	nodes,
	onBack,
	onSelectNode,
}: NodePanelGroupDrilldownProps) {
	const group = groupMeta(groupId);
	const Icon = groupLucideIcon(groupId);
	const [query, setQuery] = useState("");
	const searchRef = useRef<HTMLInputElement | null>(null);

	const filtered = useMemo(() => {
		const q = query.trim();
		if (!q) return nodes;
		return nodes.filter((entry) => matchesNodeSearch(entry, q));
	}, [nodes, query]);

	const subgroups = useMemo(
		() => catalogSubgroups(filtered, groupId),
		[filtered, groupId],
	);

	const [openSubs, setOpenSubs] = useState<Set<string>>(() => new Set());

	useEffect(() => {
		const ids = subgroups.map((sub) => sub.id);
		setOpenSubs((prev) => {
			if (prev.size > 0) {
				return new Set(ids.filter((id) => prev.has(id)));
			}
			const initial = new Set<string>();
			if (ids.includes("Send and wait for response")) {
				initial.add("Send and wait for response");
			} else if (ids[0]) {
				initial.add(ids[0]);
			}
			return initial;
		});
	}, [subgroups]);

	useEffect(() => {
		const timer = window.setTimeout(() => searchRef.current?.focus(), 40);
		return () => window.clearTimeout(timer);
	}, []);

	const toggleSub = (id: string) => {
		setOpenSubs((prev) => {
			const next = new Set(prev);
			if (next.has(id)) next.delete(id);
			else next.add(id);
			return next;
		});
	};

	return (
		<>
			<header className="n8n-panel__head n8n-panel__head--drill">
				<button
					type="button"
					className="n8n-icon-btn n8n-icon-btn--lucide"
					onClick={onBack}
					aria-label="Retour aux catégories"
				>
					<ArrowLeft size={20} strokeWidth={2} aria-hidden />
				</button>
				<div className="n8n-panel__drill-title">
					<N8nIconBadgeDrill icon={Icon} color={group.color} />
					<h2>{group.shortTitle}</h2>
				</div>
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
			<div className="n8n-panel__list n8n-panel__list--drill">
				{subgroups.length === 0 ? (
					<p className="n8n-panel__empty">Aucun nœud dans cette catégorie.</p>
				) : (
					subgroups.map((sub) => {
						const subOpen = openSubs.has(sub.id);
						return (
							<div key={sub.id} className="n8n-panel__drill-section">
								<button
									type="button"
									className="n8n-panel__drill-section-head"
									onClick={() => toggleSub(sub.id)}
									aria-expanded={subOpen}
								>
									<span>{sub.title}</span>
									<ChevronDown
										size={16}
										strokeWidth={2}
										className={
											subOpen
												? "n8n-panel__subgroup-chevron is-open"
												: "n8n-panel__subgroup-chevron"
										}
										aria-hidden
									/>
								</button>
								{subOpen ? (
									<ul className="n8n-panel__drill-node-list">
										{sub.nodes.map((entry) => (
											<NodePanelEntry
												key={entry.node_type}
												entry={entry}
												accent={accentForNode(
													entry.node_type,
													group.color,
												)}
												onSelect={onSelectNode}
												showChevron={false}
												compact
											/>
										))}
									</ul>
								) : null}
							</div>
						);
					})
				)}
			</div>
		</>
	);
}

function N8nIconBadgeDrill({
	icon: Icon,
	color,
}: {
	icon: ReturnType<typeof groupLucideIcon>;
	color: string;
}) {
	return (
		<span
			className="n8n-lucide-badge n8n-panel__drill-badge"
			style={{ color, borderColor: `${color}55`, background: `${color}18` }}
		>
			<Icon size={18} strokeWidth={1.75} aria-hidden />
		</span>
	);
}
