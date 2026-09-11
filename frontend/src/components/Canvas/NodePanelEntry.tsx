import type { CatalogNode } from "../../lib/api";
import { nodePresentation, paletteSubtitle } from "../../config/nodeRegistry";
import { entryGlyph } from "../../lib/n8nCatalog";

type NodePanelEntryProps = {
	entry: CatalogNode;
	accent: string;
	onSelect: (entry: CatalogNode) => void;
	subtitle?: string;
};

export function NodePanelEntry({
	entry,
	accent,
	onSelect,
	subtitle,
}: NodePanelEntryProps) {
	const pres = nodePresentation(entry);
	return (
		<li>
			<button type="button" onClick={() => onSelect(entry)}>
				<em style={{ background: accent }}>{entryGlyph(entry)}</em>
				<span>
					<strong>{pres.displayName}</strong>
					<small>{paletteSubtitle(entry, subtitle)}</small>
				</span>
			</button>
		</li>
	);
}
