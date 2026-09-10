import { useEffect, useMemo, useRef, useState } from "react";
import { groupCatalog } from "../../lib/n8nCatalog";
import { useDagStore } from "../../store/dagStore";

export function NodePanelRight() {
	const open = useDagStore((s) => s.nodePanelOpen);
	const closeNodePanel = useDagStore((s) => s.closeNodePanel);
	const catalog = useDagStore((s) => s.catalog);
	const insertNodeFromPanel = useDagStore((s) => s.insertNodeFromPanel);
	const pendingConnect = useDagStore((s) => s.pendingConnect);
	const [query, setQuery] = useState("");
	const searchRef = useRef<HTMLInputElement | null>(null);

	useEffect(() => {
		if (!open) return;
		setQuery("");
		const timer = window.setTimeout(() => searchRef.current?.focus(), 40);
		return () => window.clearTimeout(timer);
	}, [open]);

	useEffect(() => {
		if (!open) return;
		const onKey = (event: KeyboardEvent) => {
			if (event.key === "Escape") closeNodePanel();
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [open, closeNodePanel]);

	const grouped = useMemo(() => {
		const needle = query.trim().toLowerCase();
		const filtered = needle
			? catalog.filter((entry) => {
					const hay = `${entry.label} ${entry.node_type} ${entry.description} ${entry.fme_group || ""}`.toLowerCase();
					return hay.includes(needle);
				})
			: catalog;
		return groupCatalog(filtered);
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
									<li key={entry.node_type}>
										<button
											type="button"
											onClick={() => insertNodeFromPanel(entry)}
										>
											<em style={{ background: group.color }}>{group.glyph}</em>
											<span>
												<strong>{entry.label}</strong>
												<small>{entry.node_type}</small>
											</span>
										</button>
									</li>
								))}
							</ul>
						)}
					</section>
				))}
			</div>
		</aside>
	);
}
