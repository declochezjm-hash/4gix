import type { Connection, Edge, Node } from "@xyflow/react";

import type { FlowNodeData } from "./api";
import {
	buildCanvasEdge,
	type EdgePathStyle,
	normalizeCanvasEdges,
} from "./canvasEdges";

export function computeComposerRemoveIds(
	anchorNodeId: string,
	replaceDownstream: boolean,
	_nodes: Node<FlowNodeData>[],
	edges: Edge[],
): string[] {
	const remove = new Set<string>([anchorNodeId]);
	if (!replaceDownstream) return [...remove];
	const queue = [anchorNodeId];
	while (queue.length) {
		const id = queue.shift();
		if (!id) continue;
		for (const edge of edges) {
			if (edge.source === id && !remove.has(edge.target)) {
				remove.add(edge.target);
				queue.push(edge.target);
			}
		}
	}
	return [...remove];
}

export function materializeComposerNode(
	node: Node<FlowNodeData>,
): Node<FlowNodeData> {
	const { isGhost: _ghost, ...data } = node.data;
	return {
		...node,
		draggable: true,
		selectable: true,
		data: { ...data, isGhost: undefined },
	};
}

export function materializeComposerEdge(
	edge: Edge,
	pathStyle: EdgePathStyle,
): Edge {
	const connection: Connection = {
		source: edge.source,
		target: edge.target,
		sourceHandle: edge.sourceHandle ?? "output",
		targetHandle: edge.targetHandle ?? "input",
	};
	return normalizeCanvasEdges(
		[
			{
				...buildCanvasEdge(connection, pathStyle),
				id: edge.id,
			},
		],
		pathStyle,
	)[0];
}

export function applyComposerGraphReplacement(
	nodes: Node<FlowNodeData>[],
	edges: Edge[],
	pathStyle: EdgePathStyle,
	anchorNodeId: string,
	removeNodeIds: string[],
	proposedNodes: Node<FlowNodeData>[],
	proposedEdges: Edge[],
): { nodes: Node<FlowNodeData>[]; edges: Edge[] } {
	const remove = new Set(removeNodeIds);
	const nextNodes = proposedNodes.map((node) => materializeComposerNode(node));
	const nextEdges = proposedEdges.map((edge) =>
		materializeComposerEdge(edge, pathStyle),
	);
	const proposedIds = new Set(nextNodes.map((node) => node.id));

	const externalIn = edges.filter(
		(edge) => remove.has(edge.target) && !remove.has(edge.source),
	);
	const externalOut = edges.filter(
		(edge) => remove.has(edge.source) && !remove.has(edge.target),
	);

	const keptNodes = nodes.filter((node) => !remove.has(node.id));
	const keptEdges = edges.filter(
		(edge) => !remove.has(edge.source) && !remove.has(edge.target),
	);

	let allEdges = normalizeCanvasEdges([...keptEdges, ...nextEdges], pathStyle);

	const heads = nextNodes.filter(
		(node) =>
			!nextEdges.some(
				(edge) => edge.target === node.id && proposedIds.has(edge.source),
			),
	);
	const tails = nextNodes.filter(
		(node) =>
			!nextEdges.some(
				(edge) => edge.source === node.id && proposedIds.has(edge.target),
			),
	);

	const anchorIn =
		externalIn.find((edge) => edge.target === anchorNodeId) ?? externalIn[0];
	const anchorOut =
		externalOut.find((edge) => edge.source === anchorNodeId) ?? externalOut[0];

	if (anchorIn && heads.length) {
		const head = heads[0];
		allEdges = normalizeCanvasEdges(
			[
				...allEdges,
				buildCanvasEdge(
					{
						source: anchorIn.source,
						target: head.id,
						sourceHandle: anchorIn.sourceHandle ?? "output",
						targetHandle:
							anchorIn.targetHandle ?? head.data.inputHandles?.[0] ?? "input",
					},
					pathStyle,
				),
			],
			pathStyle,
		);
	}

	if (anchorOut && tails.length) {
		const tail = tails[0];
		allEdges = normalizeCanvasEdges(
			[
				...allEdges,
				buildCanvasEdge(
					{
						source: tail.id,
						target: anchorOut.target,
						sourceHandle:
							tail.data.outputHandles?.[0] ??
							anchorOut.sourceHandle ??
							"output",
						targetHandle: anchorOut.targetHandle ?? "input",
					},
					pathStyle,
				),
			],
			pathStyle,
		);
	}

	return { nodes: [...keptNodes, ...nextNodes], edges: allEdges };
}

export function extractContextMentions(prompt: string): string[] {
	const mentions = new Set<string>();
	for (const match of prompt.matchAll(/@([\w.-]+)/g)) {
		mentions.add(`@${match[1]}`);
	}
	return [...mentions];
}

export function toolCallBadgeLabel(summary?: string, tool?: string): string {
	const text = (summary || tool || "").toLowerCase();
	if (text.includes("attribute_filter") || text.includes("filter")) {
		return "+ Created Filter Node";
	}
	if (text.includes("gpkg") || text.includes("writer")) {
		return "+ Created Writer Node";
	}
	if (text.includes("python") || text.includes("code")) {
		return "+ Updated Code Node";
	}
	if (text.includes("connect")) return "⟷ Connected Ports";
	if (text.includes("inspect")) return "◎ Inspected Schema";
	if (summary) return summary;
	return tool || "Tool";
}
