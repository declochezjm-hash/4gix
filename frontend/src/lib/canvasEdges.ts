import type { Connection, Edge } from "@xyflow/react";

/** `default` = courbes Bézier (n8n) ; `step` = angles droits ; `smoothstep` = coudes arrondis */
export type EdgePathStyle = "default" | "step" | "smoothstep";

export function normalizeCanvasEdges(
	edges: Edge[],
	pathStyle: EdgePathStyle,
): Edge[] {
	return edges.map((edge) => ({
		...edge,
		type: pathStyle,
		interactionWidth: edge.interactionWidth ?? 22,
		style: {
			stroke: "#8a8d93",
			strokeWidth: 2,
			...edge.style,
		},
	}));
}

export function buildCanvasEdge(
	connection: Connection,
	pathStyle: EdgePathStyle,
): Connection & Pick<Edge, "type" | "interactionWidth" | "style"> {
	return {
		...connection,
		type: pathStyle,
		interactionWidth: 22,
		style: { stroke: "#8a8d93", strokeWidth: 2 },
	};
}

export function stripEdgesFromSourceHandle(
	edges: Edge[],
	connection: Connection,
): Edge[] {
	return edges.filter(
		(edge) =>
			!(
				edge.source === connection.source &&
				(edge.sourceHandle || "output") ===
					(connection.sourceHandle || "output")
			),
	);
}
