import {
	addEdge,
	applyEdgeChanges,
	applyNodeChanges,
	type Connection,
	type Edge,
	type EdgeChange,
	type Node,
	type NodeChange,
	reconnectEdge,
} from "@xyflow/react";
import { create } from "zustand";

import { enrichCatalog } from "../config/nodeRegistry";
import {
	type CatalogNode,
	type DataUploadResult,
	downloadExportFmw,
	type ExecutionResult,
	type FlowNodeData,
	type FmwImportResult,
	fetchCatalog,
	fetchNodeSnapshot,
	fetchWorkflows,
	importFmwFile,
	isFmwFilename,
	isShapefileZipFilename,
	isSpatialDataFilename,
	type MapViewState,
	type NodeSnapshot,
	saveWorkflow,
	uploadDataFile,
	type WorkflowRecord,
	wsExecuteUrl,
	zipLooksLikeShapefile,
} from "../lib/api";
import {
	buildCanvasEdge,
	type EdgePathStyle,
	normalizeCanvasEdges,
	stripEdgesFromSourceHandle,
} from "../lib/canvasEdges";

type NodeStatus = NonNullable<FlowNodeData["status"]>;

export type PendingConnect = {
	nodeId: string;
	handleId: string;
};

export type ContextMenuState = {
	nodeId: string;
	x: number;
	y: number;
};

type DagState = {
	nodes: Node<FlowNodeData>[];
	edges: Edge[];
	catalog: CatalogNode[];
	catalogLoaded: boolean;
	workflows: WorkflowRecord[];
	workflowId: string | null;
	workflowName: string;
	selectedNodeId: string | null;
	snapshots: Record<string, NodeSnapshot>;
	lastExecution: ExecutionResult | null;
	running: boolean;
	error: string | null;
	importNotice: string | null;
	inspectorOpen: boolean;
	nodePanelOpen: boolean;
	pendingConnect: PendingConnect | null;
	contextMenu: ContextMenuState | null;
	nodeClipboard: Node<FlowNodeData> | null;
	canvasLocked: boolean;
	edgePathStyle: EdgePathStyle;
	mapView: MapViewState | null;
	onNodesChange: (changes: NodeChange<Node<FlowNodeData>>[]) => void;
	onEdgesChange: (changes: EdgeChange<Edge>[]) => void;
	onConnect: (connection: Connection) => void;
	onReconnect: (oldEdge: Edge, connection: Connection) => void;
	removeEdge: (edgeId: string) => void;
	setEdgePathStyle: (style: EdgePathStyle) => void;
	addCatalogNode: (
		entry: CatalogNode,
		position?: { x: number; y: number },
	) => string;
	insertNodeFromPanel: (entry: CatalogNode) => void;
	selectNode: (id: string | null) => void;
	openInspector: (id?: string | null) => void;
	openNodePanel: (pending?: PendingConnect | null) => void;
	closeNodePanel: () => void;
	updateNodeParams: (id: string, params: Record<string, unknown>) => void;
	updateNodeData: (id: string, patch: Partial<FlowNodeData>) => void;
	setMapView: (view: MapViewState) => void;
	setWorkflowName: (name: string) => void;
	loadCatalog: () => Promise<void>;
	loadWorkflows: () => Promise<void>;
	loadWorkflow: (id: string) => void;
	saveCurrentWorkflow: () => Promise<void>;
	runDag: () => Promise<void>;
	runSelectedNode: () => Promise<void>;
	closeInspector: () => void;
	openContextMenu: (menu: ContextMenuState) => void;
	closeContextMenu: () => void;
	deleteNode: (id: string) => void;
	duplicateNode: (id: string) => void;
	copyNode: (id: string) => void;
	pasteNode: () => void;
	toggleNodeDisabled: (id: string) => void;
	renameSelectedNode: (id: string) => void;
	tidyUpWorkflow: () => void;
	loadImportedDefinition: (payload: FmwImportResult) => void;
	importFmwFromFile: (file: File) => Promise<void>;
	importLocalWorkflowFile: (file: File) => Promise<void>;
	importShapefileZipFromFile: (
		file: File,
		position?: { x: number; y: number },
	) => Promise<void>;
	importDataFileFromDrop: (
		file: File,
		position?: { x: number; y: number },
	) => Promise<void>;
	exportCurrentFmw: () => Promise<void>;
	setCanvasLocked: (locked: boolean) => void;
};

function schemaDefaults(entry: CatalogNode): Record<string, unknown> {
	const params: Record<string, unknown> = {};
	const properties = entry.schema.properties || {};
	for (const [key, prop] of Object.entries(properties)) {
		if (prop.default !== undefined) {
			params[key] = prop.default;
		}
	}
	return params;
}

function graphPayload(
	nodes: Node<FlowNodeData>[],
	edges: Edge[],
	extra: Record<string, unknown> = {},
) {
	return {
		...extra,
		nodes: nodes.map((node) => ({
			id: node.id,
			type: node.data.nodeType,
			params: node.data.params,
			position: node.position,
			data: node.data,
		})),
		edges: edges.map((edge) => ({
			id: edge.id,
			source: edge.source,
			target: edge.target,
			sourceHandle: edge.sourceHandle,
			targetHandle: edge.targetHandle,
		})),
	};
}

function activeNodes(nodes: Node<FlowNodeData>[]) {
	return nodes.filter((node) => !node.data.disabled);
}

function activeEdges(edges: Edge[], nodes: Node<FlowNodeData>[]) {
	const activeIds = new Set(activeNodes(nodes).map((node) => node.id));
	return edges.filter(
		(edge) => activeIds.has(edge.source) && activeIds.has(edge.target),
	);
}

function topologicalLayers(
	nodes: Node<FlowNodeData>[],
	edges: Edge[],
): Map<string, number> {
	const ids = new Set(nodes.map((node) => node.id));
	const incoming = new Map<string, string[]>();
	for (const id of ids) incoming.set(id, []);
	for (const edge of edges) {
		if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
		incoming.get(edge.target)?.push(edge.source);
	}
	const layer = new Map<string, number>();
	const queue = [...ids].filter((id) => (incoming.get(id) || []).length === 0);
	for (const id of queue) layer.set(id, 0);
	let head = 0;
	while (head < queue.length) {
		const current = queue[head++];
		const nextLayer = (layer.get(current) || 0) + 1;
		for (const edge of edges) {
			if (edge.source !== current || !ids.has(edge.target)) continue;
			const prev = layer.get(edge.target);
			if (prev == null || nextLayer > prev) {
				layer.set(edge.target, nextLayer);
				queue.push(edge.target);
			}
		}
	}
	for (const id of ids) {
		if (!layer.has(id)) layer.set(id, 0);
	}
	return layer;
}

function applyStatus(
	nodes: Node<FlowNodeData>[],
	nodeId: string,
	status: NodeStatus,
	extra: Partial<FlowNodeData> = {},
) {
	return nodes.map((node) =>
		node.id === nodeId
			? { ...node, data: { ...node.data, status, ...extra } }
			: node,
	);
}

function ancestorsOf(nodeId: string, edges: Edge[]): Set<string> {
	const incoming = new Map<string, string[]>();
	for (const edge of edges) {
		const list = incoming.get(edge.target) || [];
		list.push(edge.source);
		incoming.set(edge.target, list);
	}
	const seen = new Set<string>();
	const stack = [nodeId];
	while (stack.length) {
		const id = stack.pop() as string;
		if (seen.has(id)) continue;
		seen.add(id);
		for (const parent of incoming.get(id) || []) stack.push(parent);
	}
	return seen;
}

function buildNode(entry: CatalogNode, position: { x: number; y: number }) {
	const id = `${entry.node_type}-${nodeSeq++}`;
	const node: Node<FlowNodeData> = {
		id,
		type: "etl",
		position,
		data: {
			label: entry.label,
			nodeType: entry.node_type,
			category: entry.category,
			isSpatial: entry.is_spatial,
			params: schemaDefaults(entry),
			schema: entry.schema,
			status: "idle",
			inputHandles: entry.input_handles || ["input"],
			outputHandles: entry.output_handles || ["output"],
			paletteGroup: entry.palette_group || "",
			notes: "",
			disabled: false,
		},
	};
	return node;
}

let nodeSeq = 1;

export const useDagStore = create<DagState>((set, get) => ({
	nodes: [],
	edges: [],
	catalog: [],
	catalogLoaded: false,
	workflows: [],
	workflowId: null,
	workflowName: "Nouveau workflow",
	selectedNodeId: null,
	snapshots: {},
	lastExecution: null,
	running: false,
	error: null,
	importNotice: null,
	inspectorOpen: false,
	nodePanelOpen: false,
	pendingConnect: null,
	contextMenu: null,
	nodeClipboard: null,
	canvasLocked: false,
	edgePathStyle: "default",
	mapView: null,

	onNodesChange: (changes) =>
		set({ nodes: applyNodeChanges(changes, get().nodes) }),

	onEdgesChange: (changes) =>
		set({ edges: applyEdgeChanges(changes, get().edges) }),

	onConnect: (connection) => {
		const pathStyle = get().edgePathStyle;
		const base = stripEdgesFromSourceHandle(get().edges, connection);
		set({
			edges: addEdge(buildCanvasEdge(connection, pathStyle), base),
			pendingConnect: null,
		});
	},

	onReconnect: (oldEdge, connection) => {
		const without = get().edges.filter((edge) => edge.id !== oldEdge.id);
		const stripped = stripEdgesFromSourceHandle(without, connection);
		set({
			edges: reconnectEdge(
				{ ...oldEdge, type: get().edgePathStyle },
				connection,
				stripped,
			),
		});
	},

	removeEdge: (edgeId) =>
		set({ edges: get().edges.filter((edge) => edge.id !== edgeId) }),

	setEdgePathStyle: (style) =>
		set({
			edgePathStyle: style,
			edges: normalizeCanvasEdges(get().edges, style),
		}),

	addCatalogNode: (entry, position) => {
		const node = buildNode(
			entry,
			position || {
				x: 120 + (nodeSeq % 5) * 40,
				y: 80 + nodeSeq * 28,
			},
		);
		set({
			nodes: [...get().nodes, node],
			selectedNodeId: node.id,
			inspectorOpen: false,
			nodePanelOpen: false,
			pendingConnect: null,
		});
		return node.id;
	},

	insertNodeFromPanel: (entry) => {
		const { pendingConnect, selectedNodeId, nodes, edges } = get();
		const sourceId = pendingConnect?.nodeId || selectedNodeId;
		const source = nodes.find((node) => node.id === sourceId);
		const position = source
			? { x: source.position.x + 240, y: source.position.y }
			: { x: 280 + (nodes.length % 4) * 40, y: 140 + nodes.length * 12 };
		const node = buildNode(entry, position);
		let nextEdges = edges;
		if (source) {
			const sourceHandle =
				pendingConnect?.handleId || source.data.outputHandles?.[0] || "output";
			const targetHandle = entry.input_handles?.[0] || "input";
			const link: Connection = {
				source: source.id,
				sourceHandle,
				target: node.id,
				targetHandle,
			};
			nextEdges = addEdge(
				buildCanvasEdge(link, get().edgePathStyle),
				stripEdgesFromSourceHandle(edges, link),
			);
		}
		set({
			nodes: [...nodes, node],
			edges: nextEdges,
			selectedNodeId: node.id,
			nodePanelOpen: false,
			pendingConnect: null,
			inspectorOpen: false,
		});
	},

	selectNode: (id) => {
		set({ selectedNodeId: id });
	},

	openInspector: (id) => {
		const nodeId = id ?? get().selectedNodeId;
		if (!nodeId) return;
		set({
			selectedNodeId: nodeId,
			inspectorOpen: true,
			nodePanelOpen: false,
		});
		const executionId = get().lastExecution?.execution_id;
		if (!executionId) return;
		const existing = get().snapshots[nodeId];
		if (
			existing?.input_snapshot !== undefined ||
			existing?.output_snapshot !== undefined
		)
			return;
		void fetchNodeSnapshot(executionId, nodeId)
			.then((remote) => {
				set({
					snapshots: {
						...get().snapshots,
						[nodeId]: {
							...(existing || {
								node_id: nodeId,
								node_type: "",
								status: "COMPLETED",
								duration_ms: remote.execution_time_ms,
								metadata: {},
								preview: remote.output_snapshot,
							}),
							input_snapshot: remote.input_snapshot,
							output_snapshot: remote.output_snapshot,
							duration_ms: remote.execution_time_ms,
						},
					},
				});
			})
			.catch(() => undefined);
	},

	openNodePanel: (pending = null) =>
		set({
			nodePanelOpen: true,
			pendingConnect: pending,
			inspectorOpen: false,
		}),

	closeNodePanel: () => set({ nodePanelOpen: false, pendingConnect: null }),

	updateNodeParams: (id, params) =>
		set({
			nodes: get().nodes.map((node) =>
				node.id === id
					? {
							...node,
							data: {
								...node.data,
								params: { ...node.data.params, ...params },
							},
						}
					: node,
			),
		}),

	updateNodeData: (id, patch) =>
		set({
			nodes: get().nodes.map((node) =>
				node.id === id ? { ...node, data: { ...node.data, ...patch } } : node,
			),
		}),

	setMapView: (view) => set({ mapView: view }),
	setWorkflowName: (name) => set({ workflowName: name }),
	closeInspector: () => set({ inspectorOpen: false }),

	loadCatalog: async () => {
		try {
			const payload = await fetchCatalog();
			const nodes = enrichCatalog(payload.nodes || []);
			set({
				catalog: nodes,
				catalogLoaded: true,
				error: nodes.length
					? null
					: "Catalogue vide — redémarrez l’API backend (port 8000).",
			});
		} catch (err) {
			set({
				catalog: [],
				catalogLoaded: true,
				error:
					err instanceof Error
						? err.message
						: "Erreur catalogue (API injoignable ?)",
			});
		}
	},

	loadWorkflows: async () => {
		try {
			const payload = await fetchWorkflows();
			set({ workflows: payload.workflows });
		} catch (err) {
			set({ error: err instanceof Error ? err.message : "Erreur workflows" });
		}
	},

	loadWorkflow: (id) => {
		const record = get().workflows.find((item) => item.id === id);
		if (!record) return;
		const definition = record.definition || {};
		const nodes = ((definition.nodes || []) as Node<FlowNodeData>[]).map(
			(node) => ({
				...node,
				type: "etl",
				data: {
					...node.data,
					status: "idle" as const,
					durationMs: undefined,
					error: null,
				},
			}),
		);
		set({
			workflowId: record.id,
			workflowName: record.name,
			nodes,
			edges: normalizeCanvasEdges(
				(definition.edges || []) as Edge[],
				get().edgePathStyle,
			),
			snapshots: {},
			lastExecution: null,
			selectedNodeId: null,
			inspectorOpen: false,
			nodePanelOpen: false,
		});
	},

	saveCurrentWorkflow: async () => {
		const { workflowName, workflowId, nodes, edges } = get();
		try {
			const saved = await saveWorkflow({
				id: workflowId,
				name: workflowName || "Sans nom",
				definition: { nodes, edges },
			});
			set({
				workflowId: saved.id,
				workflowName: saved.name,
				error: null,
			});
			await get().loadWorkflows();
		} catch (err) {
			set({
				error: err instanceof Error ? err.message : "Échec de sauvegarde",
			});
		}
	},

	runDag: async () => {
		await executeViaSocket(get, set);
	},

	runSelectedNode: async () => {
		const { selectedNodeId, nodes, edges } = get();
		if (!selectedNodeId) {
			await executeViaSocket(get, set);
			return;
		}
		const keep = ancestorsOf(selectedNodeId, edges);
		await executeViaSocket(
			get,
			set,
			nodes.filter((node) => keep.has(node.id)),
			edges.filter((edge) => keep.has(edge.source) && keep.has(edge.target)),
		);
	},

	openContextMenu: (menu) =>
		set({ contextMenu: menu, selectedNodeId: menu.nodeId }),
	closeContextMenu: () => set({ contextMenu: null }),

	deleteNode: (id) =>
		set({
			nodes: get().nodes.filter((node) => node.id !== id),
			edges: get().edges.filter(
				(edge) => edge.source !== id && edge.target !== id,
			),
			selectedNodeId: get().selectedNodeId === id ? null : get().selectedNodeId,
			contextMenu: null,
		}),

	duplicateNode: (id) => {
		const source = get().nodes.find((node) => node.id === id);
		if (!source) return;
		const copy: Node<FlowNodeData> = {
			...source,
			id: `${source.data.nodeType}-${nodeSeq++}`,
			position: {
				x: source.position.x + 40,
				y: source.position.y + 40,
			},
			data: {
				...source.data,
				status: "idle",
				durationMs: undefined,
				error: null,
			},
		};
		set({
			nodes: [...get().nodes, copy],
			selectedNodeId: copy.id,
			contextMenu: null,
		});
	},

	copyNode: (id) => {
		const source = get().nodes.find((node) => node.id === id);
		if (!source) return;
		set({
			nodeClipboard: JSON.parse(JSON.stringify(source)) as Node<FlowNodeData>,
			contextMenu: null,
		});
	},

	pasteNode: () => {
		const clip = get().nodeClipboard;
		if (!clip) return;
		const copy: Node<FlowNodeData> = {
			...clip,
			id: `${clip.data.nodeType}-${nodeSeq++}`,
			position: {
				x: (clip.position?.x || 0) + 60,
				y: (clip.position?.y || 0) + 60,
			},
			data: {
				...clip.data,
				status: "idle",
				durationMs: undefined,
				error: null,
			},
		};
		set({ nodes: [...get().nodes, copy], selectedNodeId: copy.id });
	},

	toggleNodeDisabled: (id) =>
		set({
			nodes: get().nodes.map((node) =>
				node.id === id
					? { ...node, data: { ...node.data, disabled: !node.data.disabled } }
					: node,
			),
			contextMenu: null,
		}),

	renameSelectedNode: (id) => {
		const node = get().nodes.find((item) => item.id === id);
		if (!node) return;
		const next = window.prompt("Renommer le nœud", node.data.label);
		if (!next?.trim()) return;
		set({
			nodes: get().nodes.map((item) =>
				item.id === id
					? { ...item, data: { ...item.data, label: next.trim() } }
					: item,
			),
			contextMenu: null,
		});
	},

	tidyUpWorkflow: () => {
		const { nodes, edges } = get();
		if (!nodes.length) return;
		const layers = topologicalLayers(nodes, edges);
		const byLayer = new Map<number, Node<FlowNodeData>[]>();
		for (const node of nodes) {
			const layer = layers.get(node.id) || 0;
			const list = byLayer.get(layer) || [];
			list.push(node);
			byLayer.set(layer, list);
		}
		const positioned = nodes.map((node) => {
			const layer = layers.get(node.id) || 0;
			const peers = byLayer.get(layer) || [];
			const index = peers.findIndex((peer) => peer.id === node.id);
			return {
				...node,
				position: { x: 80 + layer * 260, y: 80 + index * 130 },
			};
		});
		set({ nodes: positioned, contextMenu: null });
	},

	loadImportedDefinition: (payload) => {
		const catalog = get().catalog;
		const nodes = (payload.definition.nodes || []).map((raw) => {
			const node = raw as Node<FlowNodeData>;
			const entry = catalog.find(
				(item) => item.node_type === node.data?.nodeType,
			);
			return {
				...node,
				type: "etl",
				data: {
					...node.data,
					params: {
						...(entry ? schemaDefaults(entry) : {}),
						...(node.data?.params || {}),
					},
					schema: node.data?.schema || entry?.schema,
					inputHandles: node.data?.inputHandles ||
						entry?.input_handles || ["input"],
					outputHandles: node.data?.outputHandles ||
						entry?.output_handles || ["output"],
					status: "idle" as const,
					disabled: false,
				},
			};
		});
		set({
			nodes,
			edges: normalizeCanvasEdges(
				(payload.definition.edges || []) as Edge[],
				get().edgePathStyle,
			),
			workflowName: payload.name,
			workflowId: null,
			snapshots: {},
			lastExecution: null,
			selectedNodeId: null,
			inspectorOpen: false,
			nodePanelOpen: false,
			error: null,
			importNotice:
				payload.warnings?.length > 0
					? `Import .fmw : ${nodes.length} nœud(s), ${(payload.definition.edges || []).length} lien(s) · ${payload.warnings[0]}`
					: `Import .fmw : ${nodes.length} nœud(s), ${(payload.definition.edges || []).length} lien(s) chargés.`,
		});
	},

	importFmwFromFile: async (file: File) => {
		if (!isFmwFilename(file.name)) {
			set({ error: "Fichier attendu: .fmw ou .fmwt" });
			return;
		}
		try {
			const payload = await importFmwFile(file);
			get().loadImportedDefinition(payload);
		} catch (err) {
			set({
				error: err instanceof Error ? err.message : "Import .fmw impossible.",
				importNotice: null,
			});
		}
	},

	importLocalWorkflowFile: async (file: File) => {
		const lower = file.name.toLowerCase();
		if (isFmwFilename(file.name)) {
			await get().importFmwFromFile(file);
			return;
		}
		if (isSpatialDataFilename(file.name)) {
			await get().importDataFileFromDrop(file);
			return;
		}
		if (!lower.endsWith(".json") && !lower.endsWith(".4gix.json")) {
			set({
				error:
					"Formats acceptés: .fmw, .fmwt, .json, .zip (Shapefile), .geojson, .tif",
			});
			return;
		}
		try {
			const raw = JSON.parse(await file.text()) as {
				name?: string;
				nodes?: unknown[];
				edges?: unknown[];
				definition?: { nodes?: unknown[]; edges?: unknown[] };
			};
			const payload: FmwImportResult = {
				name: raw.name || file.name.replace(/\.[^.]+$/, ""),
				format: "4gix_dag",
				source: "json_file",
				warnings: [],
				definition: {
					nodes: raw.definition?.nodes ?? raw.nodes ?? [],
					edges: raw.definition?.edges ?? raw.edges ?? [],
				},
			};
			if (!payload.definition.nodes.length) {
				set({ error: "JSON invalide: aucun nœud trouvé." });
				return;
			}
			get().loadImportedDefinition(payload);
		} catch (err) {
			set({
				error: err instanceof Error ? err.message : "Import JSON impossible.",
			});
		}
	},

	importDataFileFromDrop: async (file, position) => {
		if (!isSpatialDataFilename(file.name)) {
			set({
				error:
					"Formats de données acceptés : .zip (Shapefile), .geojson, .tif / .tiff.",
			});
			return;
		}
		if (isShapefileZipFilename(file.name)) {
			const looksLike = await zipLooksLikeShapefile(file);
			if (!looksLike) {
				set({
					error:
						"Ce .zip ne semble pas contenir de Shapefile (.shp, .shx, .dbf).",
				});
				return;
			}
		}
		try {
			const payload: DataUploadResult = await uploadDataFile(file);
			const suggested = payload.suggested_node;
			if (!suggested?.node_type) {
				throw new Error(
					"Réponse serveur incomplète (suggested_node manquant).",
				);
			}
			const entry = get().catalog.find(
				(item) => item.node_type === suggested.node_type,
			);
			if (!entry) {
				set({
					error: `Nœud ${suggested.node_type} absent du catalogue.`,
				});
				return;
			}
			const pos =
				position ||
				({
					x: 120 + (get().nodes.length % 5) * 48,
					y: 80 + get().nodes.length * 24,
				} as const);
			const node = buildNode(entry, pos);
			node.data.label = suggested.label || entry.label;
			node.data.params = {
				...node.data.params,
				...suggested.params,
			};
			const typeLabels: Record<string, string> = {
				shapefile: "Shapefile",
				geojson: "GeoJSON",
				geotiff: "GeoTIFF",
			};
			const kind = typeLabels[payload.detected_type] || payload.detected_type;
			set({
				nodes: [...get().nodes, node],
				selectedNodeId: node.id,
				inspectorOpen: true,
				nodePanelOpen: false,
				error: null,
				importNotice: `${kind} · ${file.name}`,
			});
		} catch (err) {
			set({
				error:
					err instanceof Error ? err.message : "Import de données impossible.",
				importNotice: null,
			});
		}
	},

	importShapefileZipFromFile: async (file, position) => {
		await get().importDataFileFromDrop(file, position);
	},

	exportCurrentFmw: async () => {
		const state = get();
		if (!state.nodes.length) {
			set({ error: "Aucun nœud à exporter." });
			return;
		}
		await get().saveCurrentWorkflow();
		const workflowId = get().workflowId;
		if (!workflowId) {
			set({ error: "Enregistrez le workflow avant l'export .fmw." });
			return;
		}
		try {
			const base = (get().workflowName || "workflow").replace(
				/[<>:"/\\|?*]+/g,
				"_",
			);
			await downloadExportFmw(workflowId, base);
			set({ error: null });
		} catch (err) {
			set({
				error: err instanceof Error ? err.message : "Export .fmw impossible.",
			});
		}
	},

	setCanvasLocked: (locked) => set({ canvasLocked: locked }),
}));

async function executeViaSocket(
	get: () => DagState,
	set: (
		partial: Partial<DagState> | ((state: DagState) => Partial<DagState>),
	) => void,
	subsetNodes?: Node<FlowNodeData>[],
	subsetEdges?: Edge[],
) {
	const { workflowId, workflowName } = get();
	const baseNodes = subsetNodes || get().nodes;
	const baseEdges = subsetEdges || get().edges;
	const nodes = activeNodes(baseNodes);
	const edges = activeEdges(baseEdges, baseNodes);
	const targetIds = new Set(nodes.map((node) => node.id));
	set({
		running: true,
		error: null,
		mapView: null,
		nodes: get().nodes.map((node) =>
			targetIds.has(node.id)
				? {
						...node,
						data: {
							...node.data,
							status: "idle",
							durationMs: undefined,
							error: null,
						},
					}
				: node,
		),
	});

	const payload = graphPayload(nodes, edges, {
		name: workflowName,
		workflow_id: workflowId,
	});

	await new Promise<void>((resolve) => {
		let settled = false;
		const finish = () => {
			if (settled) return;
			settled = true;
			resolve();
		};

		try {
			const socket = new WebSocket(wsExecuteUrl());
			socket.onopen = () => socket.send(JSON.stringify(payload));
			socket.onmessage = (event) => {
				const message = JSON.parse(event.data) as {
					type: string;
					payload: Record<string, unknown>;
				};
				if (message.type === "node_running") {
					const nodeId = String(message.payload.node_id || "");
					set({ nodes: applyStatus(get().nodes, nodeId, "RUNNING") });
				}
				if (message.type === "snapshot") {
					const snapshot = message.payload as unknown as NodeSnapshot;
					const failed =
						snapshot.status === "FAILED" || snapshot.status === "error";
					set({
						snapshots: { ...get().snapshots, [snapshot.node_id]: snapshot },
						nodes: applyStatus(
							get().nodes,
							snapshot.node_id,
							failed ? "FAILED" : "COMPLETED",
							{
								durationMs: snapshot.duration_ms,
								error: snapshot.error || null,
							},
						),
					});
				}
				if (message.type === "completed" || message.type === "failed") {
					const result = message.payload as unknown as ExecutionResult;
					const snapshots: Record<string, NodeSnapshot> = {
						...get().snapshots,
					};
					for (const snapshot of result.snapshots || []) {
						snapshots[snapshot.node_id] = snapshot;
					}
					set({
						lastExecution: result,
						snapshots,
						running: false,
						error:
							result.status === "FAILED" || result.status === "error"
								? result.error || "Échec d'exécution"
								: null,
						nodes: get().nodes.map((node) => {
							const snap = snapshots[node.id];
							if (!snap) return node;
							const failed =
								snap.status === "FAILED" || snap.status === "error";
							return {
								...node,
								data: {
									...node.data,
									status: failed ? "FAILED" : "COMPLETED",
									durationMs: snap.duration_ms,
									error: snap.error || null,
								},
							};
						}),
					});
					finish();
				}
				if (message.type === "error") {
					set({
						running: false,
						error: String(message.payload.error || "Erreur WebSocket"),
					});
					finish();
				}
			};
			socket.onerror = () => {
				set({ running: false, error: "Connexion WebSocket impossible." });
				finish();
			};
			socket.onclose = () => {
				if (get().running) {
					set({ running: false });
				}
				finish();
			};
		} catch (err) {
			set({
				running: false,
				error: err instanceof Error ? err.message : "Échec d'exécution",
			});
			finish();
		}
	});
}
