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
	mapView: MapViewState | null;
	onNodesChange: (changes: NodeChange<Node<FlowNodeData>>[]) => void;
	onEdgesChange: (changes: EdgeChange<Edge>[]) => void;
	onConnect: (connection: Connection) => void;
	addCatalogNode: (
		entry: CatalogNode,
		position?: { x: number; y: number },
	) => void;
	selectNode: (id: string | null) => void;
	updateNodeParams: (id: string, params: Record<string, unknown>) => void;
	setMapView: (view: MapViewState) => void;
	setWorkflowName: (name: string) => void;
	loadCatalog: () => Promise<void>;
	loadWorkflows: () => Promise<void>;
	loadWorkflow: (id: string) => void;
	saveCurrentWorkflow: () => Promise<void>;
	runDag: () => Promise<void>;
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
	mapView: null,

	onNodesChange: (changes) =>
		set({ nodes: applyNodeChanges(changes, get().nodes) }),

	onEdgesChange: (changes) =>
		set({ edges: applyEdgeChanges(changes, get().edges) }),

	onConnect: (connection) =>
		set({
			edges: addEdge(
				{ ...connection, animated: true, type: "smoothstep" },
				get().edges,
			),
		}),

	addCatalogNode: (entry, position) => {
		const id = `${entry.node_type}-${nodeSeq++}`;
		const node: Node<FlowNodeData> = {
			id,
			type: "etl",
			position: position || {
				x: 120 + (nodeSeq % 5) * 40,
				y: 80 + nodeSeq * 28,
			},
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
			},
		};
		set({
			nodes: [...get().nodes, node],
			selectedNodeId: id,
			inspectorOpen: true,
		});
	},

	selectNode: (id) => {
		set({ selectedNodeId: id, inspectorOpen: Boolean(id) });
		const executionId = get().lastExecution?.execution_id;
		if (!id || !executionId) return;
		const existing = get().snapshots[id];
		if (
			existing?.input_snapshot !== undefined ||
			existing?.output_snapshot !== undefined
		)
			return;
		void fetchNodeSnapshot(executionId, id)
			.then((remote) => {
				set({
					snapshots: {
						...get().snapshots,
						[id]: {
							...(existing || {
								node_id: id,
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
		const { nodes, edges, workflowId, workflowName } = get();
		set({
			running: true,
			error: null,
			snapshots: {},
			mapView: null,
			nodes: nodes.map((node) => ({
				...node,
				data: {
					...node.data,
					status: "idle",
					durationMs: undefined,
					error: null,
				},
			})),
		});

		const payload = graphPayload(get().nodes, edges, {
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
	},
}));
