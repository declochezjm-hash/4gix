import { useEffect, useMemo, useRef, useState } from "react";
import { matchesNodeSearch } from "../../config/nodeRegistry";
import { featuredCatalogNodes, groupCatalog } from "../../lib/n8nCatalog";
import { useDagStore } from "../../store/dagStore";
import { NodePanelEntry } from "./NodePanelEntry";

export function NodePanelRight() {
	const open = useDagStore((s) => s.nodePanelOpen);
	const closeNodePanel = useDagStore((s) => s.closeNodePanel);
	const catalog = useDagStore((s) => s.catalog);
	const insertNodeFromPanel = useDagStore((s) => s.insertNodeFromPanel);
	const loadCatalog = useDagStore((s) => s.loadCatalog);
	const pendingConnect = useDagStore((s) => s.pendingConnect);
	const [query, setQuery] = useState("");
	const searchRef = useRef<HTMLInputElement | null>(null);

	useEffect(() => {
		if (!open) return;
		setQuery("");
		void loadCatalog();
		const timer = window.setTimeout(() => searchRef.current?.focus(), 40);
		return () => window.clearTimeout(timer);
	}, [open, loadCatalog]);

	useEffect(() => {
		if (!open) return;
		const onKey = (event: KeyboardEvent) => {
			if (event.key === "Escape") closeNodePanel();
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [open, closeNodePanel]);

	const { featured, grouped } = useMemo(() => {
		const needle = query.trim().toLowerCase();
		const filtered = needle
			? catalog.filter((entry) => matchesNodeSearch(entry, needle))
			: catalog;
		return {
			featured: needle ? [] : featuredCatalogNodes(catalog),
			grouped: groupCatalog(filtered),
		};
	}, [catalog, query]);

	if (!open) return null;

	return (
		<aside className="n8n-panel" aria-label="Ajouter un nœud">
			<header className="n8n-panel__head">
				<div>
					<p className="n8n-panel__kicker">
						{pendingConnect ? "Connecter un nœud" : "Ajouter un nœud"}
					</p>
					<h2>What happens next?</h2>
				</div>
				<button
					type="button"
					className="n8n-icon-btn"
					onClick={closeNodePanel}
					aria-label="Fermer le panneau"
				>
					×
				</button>
			</header>
			<div className="n8n-panel__search">
				<input
					ref={searchRef}
					value={query}
					onChange={(event) => setQuery(event.target.value)}
					placeholder="Search nodes..."
					aria-label="Search nodes"
				/>
			</div>
			<div className="n8n-panel__list">
				{featured.length ? (
					<section className="n8n-panel__featured">
						<h3>
							<span style={{ background: "#7C3AED" }}>{"{}"}</span>
							Code &amp; transformation
						</h3>
						<ul>
							{featured.map((entry) => (
								<NodePanelEntry
									key={entry.node_type}
									entry={entry}
									accent="#7C3AED"
									onSelect={insertNodeFromPanel}
									subtitle="Éditeur Monaco · Python / SQL"
								/>
							))}
						</ul>
					</section>
				) : null}
				{grouped.map(({ group, nodes }) => (
					<section key={group.id}>
						<h3>
							<span style={{ background: group.color }}>{group.glyph}</span>
							{group.title}
						</h3>
						{nodes.length === 0 ? (
							<p className="n8n-panel__empty">Aucun nœud dans cette catégorie.</p>
						) : (
							<ul>
								{nodes.map((entry) => (
									<NodePanelEntry
										key={entry.node_type}
										entry={entry}
										accent={group.color}
										onSelect={insertNodeFromPanel}
									/>
								))}
							</ul>
						)}
					</section>
				))}
			</div>
		</aside>
	);
}
