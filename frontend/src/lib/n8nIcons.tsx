import type { LucideIcon } from "lucide-react";
import { Bot, Box, Globe, Image, Layers, Terminal, Wand2 } from "lucide-react";
import type { CatalogNode } from "./api";
import { groupIdOf, type N8nGroupId } from "./n8nCatalog";

export {
	ArrowLeft,
	Bot,
	Box,
	ChevronDown,
	ChevronRight,
	GitFork,
	Globe,
	Image,
	Layers,
	Search,
	Terminal,
	UserCheck,
	Wand2,
	Zap,
} from "lucide-react";

const GROUP_ICONS: Record<N8nGroupId, LucideIcon> = {
	ai: Bot,
	data: Wand2,
	gis: Layers,
	bim: Box,
	raster: Image,
	io: Globe,
};

export function groupLucideIcon(groupId: N8nGroupId): LucideIcon {
	return GROUP_ICONS[groupId] ?? Wand2;
}

export function catalogEntryIcon(
	entry: Pick<CatalogNode, "node_type" | "category">,
): LucideIcon {
	const type = entry.node_type || "";
	if (type === "composer_agent") {
		return Bot;
	}
	if (type === "python_caller" || type === "code_node") {
		return Terminal;
	}
	return groupLucideIcon(groupIdOf(entry));
}

type N8nIconBadgeProps = {
	icon: LucideIcon;
	color: string;
	size?: number;
	className?: string;
};

export function N8nIconBadge({
	icon: Icon,
	color,
	size = 14,
	className = "",
}: N8nIconBadgeProps) {
	return (
		<span
			className={`n8n-lucide-badge ${className}`.trim()}
			style={{ background: color }}
			aria-hidden
		>
			<Icon size={size} strokeWidth={2.5} color="#ffffff" />
		</span>
	);
}
