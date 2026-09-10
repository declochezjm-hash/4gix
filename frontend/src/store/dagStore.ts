import {
	addEdge,
	applyEdgeChanges,
	applyNodeChanges,
	type Connection,
	type Edge,
	type EdgeChange,
	type Node,
	type NodeChange,
} from "@xyflow/react";
import { create } from "zustand";

import {
	type CatalogNode,
	type ExecutionResult,
	type FlowNodeData,
	fetchCatalog,
	fetchNodeSnapshot,
	fetchWorkflows,
	type MapViewState,
	type NodeSnapshot,
	saveWorkflow,
	type WorkflowRecord,
	wsExecuteUrl,
} from "../lib/api";

type NodeStatus = NonNullable<FlowNodeData["status"]>;

export type PendingConnect = {
	nodeId: string;
	handleId: string;
};

type DagState = {
	nodes: Node<FlowNodeData>[];
	edges: Edge[];
	catalog: CatalogNode[];
	workflows: WorkflowRecord[];
	workflowId: string | null;
	workflowName: string;
	selectedNodeId: string | null;
	snapshots: Record<string, NodeSnapshot>;
	lastExecution: ExecutionResult | null;
	running: boolean;
	error: string | null;
	inspectorOpen: boolean;
	nodePanelOpen: boolean;
	pendingConnect: PendingConnect | null;
	mapView: MapViewState | null;
	onNodesChange: (changes: NodeChange<Node<FlowNodeData>>[]) => void;
	onEdgesChange: (changes: EdgeChange<Edge>[]) => void;
	onConnect: (connection: Connection) => void;
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
			fmeGroup: entry.fme_group || "",
			notes: "",
		},
	};
	return node;
}

let nodeSeq = 1;

export const useDagStore = create<DagState>((set, get) => ({
	nodes: [],
	edges: [],
	catalog: [],
	workflows: [],
	workflowId: null,
	workflowName: "Nouveau workflow",
	selectedNodeId: null,
	snapshots: {},
	lastExecution: null,
	running: false,
	error: null,
	inspectorOpen: false,
	nodePanelOpen: false,
	pendingConnect: null,
	mapView: null,

	onNodesChange: (changes) =>
		set({ nodes: applyNodeChanges(changes, get().nodes) }),

	onEdgesChange: (changes) =>
		set({ edges: applyEdgeChanges(changes, get().edges) }),

	onConnect: (connection) =>
		set({
			edges: addEdge(
				{ ...connection, type: "default", animated: false },
				get().edges,
			),
			pendingConnect: null,
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
			nextEdges = addEdge(
				{
					source: source.id,
					sourceHandle,
					target: node.id,
					targetHandle,
					type: "default",
				},
				edges,
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
			const catalog = await fetchCatalog();
			set({ catalog: catalog.nodes, error: null });
		} catch (err) {
			set({ error: err instanceof Error ? err.message : "Erreur catalogue" });
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
			edges: (definition.edges || []) as Edge[],
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
			edges.filter(
				(edge) => keep.has(edge.source) && keep.has(edge.target),
			),
		);
	},
}));

async function executeViaSocket(
	get: () => DagState,
	set: (partial: Partial<DagState> | ((state: DagState) => Partial<DagState>)) => void,
	subsetNodes?: Node<FlowNodeData>[],
	subsetEdges?: Edge[],
) {
	const { workflowId, workflowName } = get();
	const nodes = subsetNodes || get().nodes;
	const edges = subsetEdges || get().edges;
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
