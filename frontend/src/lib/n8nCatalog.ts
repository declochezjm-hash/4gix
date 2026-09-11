import type { CatalogNode } from "./api";

export type N8nGroupId =
	| "ai"
	| "data"
	| "gis"
	| "bim"
	| "raster"
	| "io";

export type N8nGroup = {
	id: N8nGroupId;
	title: string;
	color: string;
	glyph: string;
};

export const N8N_GROUPS: N8nGroup[] = [
	{ id: "ai", title: "Advanced AI / ML", color: "#8B5CF6", glyph: "✦" },
	{ id: "data", title: "Data Transformation", color: "#7C3AED", glyph: "ƒ" },
	{
		id: "gis",
		title: "GIS & Spatial Analysis",
		color: "#3B82F6",
		glyph: "◎",
	},
	{ id: "bim", title: "BIM & 3D", color: "#F59E0B", glyph: "⌂" },
	{ id: "raster", title: "Raster & MNT", color: "#14B8A6", glyph: "▦" },
	{ id: "io", title: "Readers / Writers", color: "#22C55E", glyph: "▤" },
];

const TYPE_GROUP: Record<string, N8nGroupId> = {
	attribute_manager: "data",
	attribute_mapper: "data",
	attribute_filter: "data",
	tester: "data",
	test_filter: "data",
	list_exploder: "data",
	counter: "data",
	duplicate_filter: "data",
	python_caller: "data",
	code_node: "data",
	geometry_validator: "gis",
	geometry_filter: "gis",
	snapper: "gis",
	orientor: "gis",
	bufferer: "gis",
	buffer: "gis",
	clipper: "gis",
	dissolver: "gis",
	area_on_area_overlayer: "gis",
	line_on_line_overlayer: "gis",
	centroid_extractor: "gis",
	bounding_box_replacer: "gis",
	densifier: "gis",
	generalizer: "gis",
	feature_merger: "gis",
	spatial_relator: "gis",
	neighbor_finder: "gis",
	spatial_join: "gis",
	reprojector: "gis",
	reproject: "gis",
	ifc_bim_reader: "bim",
	dxf_reader: "bim",
	geotiff_raster_reader: "raster",
	raster_clipper: "raster",
	zonal_statistics: "raster",
	postgis_reader: "io",
	postgis_writer: "io",
	geojson_reader: "io",
	file_reader: "io",
	shapefile_reader: "io",
	file_writer: "io",
	log_writer: "io",
	rest_wfs_reader: "io",
};

const TYPE_GLYPH: Record<string, string> = {
	python_caller: "{}",
	code_node: "{}",
};

export function entryGlyph(
	entry: Pick<CatalogNode, "node_type" | "category">,
): string {
	const type = entry.node_type || "";
	if (TYPE_GLYPH[type]) return TYPE_GLYPH[type];
	return groupMeta(groupIdOf(entry)).glyph;
}

export function groupIdOf(entry: Pick<CatalogNode, "node_type" | "category">): N8nGroupId {
	if (TYPE_GROUP[entry.node_type]) return TYPE_GROUP[entry.node_type];
	if (entry.category === "Reader" || entry.category === "Writer") return "io";
	return "data";
}

export function groupMeta(id: N8nGroupId): N8nGroup {
	return N8N_GROUPS.find((group) => group.id === id) || N8N_GROUPS[1];
}

export function nodeChrome(entry: {
	nodeType?: string;
	node_type?: string;
	category: string;
}): N8nGroup {
	const nodeType = entry.nodeType || entry.node_type || "";
	const group = groupMeta(
		groupIdOf({
			node_type: nodeType,
			category: entry.category as CatalogNode["category"],
		}),
	);
	const glyph = TYPE_GLYPH[nodeType];
	return glyph ? { ...group, glyph } : group;
}

const CATALOG_PRIORITY = ["python_caller"];

function sortCatalogNodes(nodes: CatalogNode[]): CatalogNode[] {
	return [...nodes].sort((left, right) => {
		const li = CATALOG_PRIORITY.indexOf(left.node_type);
		const ri = CATALOG_PRIORITY.indexOf(right.node_type);
		const lRank = li === -1 ? 999 : li;
		const rRank = ri === -1 ? 999 : ri;
		if (lRank !== rRank) return lRank - rRank;
		return left.label.localeCompare(right.label, "fr");
	});
}

export function groupCatalog(nodes: CatalogNode[]): {
	group: N8nGroup;
	nodes: CatalogNode[];
}[] {
	return N8N_GROUPS.map((group) => ({
		group,
		nodes: sortCatalogNodes(
			nodes.filter((node) => groupIdOf(node) === group.id),
		),
	}));
}

export function featuredCatalogNodes(nodes: CatalogNode[]): CatalogNode[] {
	return sortCatalogNodes(
		nodes.filter((node) => CATALOG_PRIORITY.includes(node.node_type)),
	);
}
