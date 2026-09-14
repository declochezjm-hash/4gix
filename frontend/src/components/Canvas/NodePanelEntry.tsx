import { nodePresentation, paletteSubtitle } from "../../config/nodeRegistry";
import type { CatalogNode } from "../../lib/api";
import {
	ChevronRight,
	catalogEntryIcon,
	N8nIconBadge,
} from "../../lib/n8nIcons";

type NodePanelEntryProps = {
	entry: CatalogNode;
	accent: string;
	onSelect: (entry: CatalogNode) => void;
	subtitle?: string;
	showChevron?: boolean;
	compact?: boolean;
};

export function NodePanelEntry({
	entry,
	accent,
	onSelect,
	subtitle,
	showChevron = true,
	compact = false,
}: NodePanelEntryProps) {
	const pres = nodePresentation(entry);
	const sub = paletteSubtitle(entry, subtitle);
	return (
		<li>
			<button
				type="button"
				className={
					compact
						? "n8n-panel__node-btn n8n-panel__node-btn--compact"
						: "n8n-panel__node-btn"
				}
				onClick={() => onSelect(entry)}
			>
				<N8nIconBadge icon={catalogEntryIcon(entry)} color={accent} size={15} />
				<span className="n8n-panel__node-copy">
					<strong>{pres.displayName}</strong>
					{!compact && sub ? <small>{sub}</small> : null}
				</span>
				{showChevron ? (
					<ChevronRight
						size={16}
						strokeWidth={2}
						className="n8n-panel__chevron"
						aria-hidden
					/>
				) : null}
			</button>
		</li>
	);
}
