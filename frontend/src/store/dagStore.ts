import { create } from "zustand";
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

import {
  executeGraph,
  fetchCatalog,
  type CatalogNode,
  type ExecutionResult,
  type FlowNodeData,
  type NodeSnapshot,
} from "../lib/api";

type DagState = {
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  catalog: CatalogNode[];
  selectedNodeId: string | null;
  snapshots: Record<string, NodeSnapshot>;
  lastExecution: ExecutionResult | null;
  running: boolean;
  error: string | null;
  inspectorOpen: boolean;
  onNodesChange: (changes: NodeChange<Node<FlowNodeData>>[]) => void;
  onEdgesChange: (changes: EdgeChange<Edge>[]) => void;
  onConnect: (connection: Connection) => void;
  addCatalogNode: (entry: CatalogNode, position?: { x: number; y: number }) => void;
  selectNode: (id: string | null) => void;
  updateNodeParams: (id: string, params: Record<string, unknown>) => void;
  loadCatalog: () => Promise<void>;
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

let nodeSeq = 1;

export const useDagStore = create<DagState>((set, get) => ({
  nodes: [],
  edges: [],
  catalog: [],
  selectedNodeId: null,
  snapshots: {},
  lastExecution: null,
  running: false,
  error: null,
  inspectorOpen: false,

  onNodesChange: (changes) =>
    set({ nodes: applyNodeChanges(changes, get().nodes) }),

  onEdgesChange: (changes) =>
    set({ edges: applyEdgeChanges(changes, get().edges) }),

  onConnect: (connection) =>
    set({ edges: addEdge({ ...connection, animated: true }, get().edges) }),

  addCatalogNode: (entry, position) => {
    const id = `${entry.node_type}-${nodeSeq++}`;
    const node: Node<FlowNodeData> = {
      id,
      type: "etl",
      position: position || { x: 120 + (nodeSeq % 5) * 40, y: 80 + nodeSeq * 28 },
      data: {
        label: entry.label,
        nodeType: entry.node_type,
        category: entry.category,
        isSpatial: entry.is_spatial,
        params: schemaDefaults(entry),
        schema: entry.schema,
        status: "idle",
      },
    };
    set({ nodes: [...get().nodes, node], selectedNodeId: id, inspectorOpen: true });
  },

  selectNode: (id) => set({ selectedNodeId: id, inspectorOpen: Boolean(id) }),

  updateNodeParams: (id, params) =>
    set({
      nodes: get().nodes.map((node) =>
        node.id === id
          ? { ...node, data: { ...node.data, params: { ...node.data.params, ...params } } }
          : node
      ),
    }),

  closeInspector: () => set({ inspectorOpen: false }),

  loadCatalog: async () => {
    try {
      const catalog = await fetchCatalog();
      set({ catalog: catalog.nodes, error: null });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Erreur catalogue" });
    }
  },

  runDag: async () => {
    const { nodes, edges } = get();
    set({
      running: true,
      error: null,
      snapshots: {},
      nodes: nodes.map((node) => ({
        ...node,
        data: { ...node.data, status: "running" },
      })),
    });
    try {
      const payload = {
        name: "canvas-run",
        nodes: nodes.map((node) => ({
          id: node.id,
          type: node.data.nodeType,
          params: node.data.params,
          position: node.position,
        })),
        edges: edges.map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourceHandle,
          targetHandle: edge.targetHandle,
        })),
      };
      const result = await executeGraph(payload);
      const snapshots: Record<string, NodeSnapshot> = {};
      for (const snapshot of result.snapshots) {
        snapshots[snapshot.node_id] = snapshot;
      }
      set({
        lastExecution: result,
        snapshots,
        running: false,
        error: result.status === "error" ? result.error || "Échec d'exécution" : null,
        nodes: get().nodes.map((node) => {
          const snap = snapshots[node.id];
          return {
            ...node,
            data: {
              ...node.data,
              status: snap ? (snap.status === "success" ? "success" : "error") : "idle",
            },
          };
        }),
      });
    } catch (err) {
      set({
        running: false,
        error: err instanceof Error ? err.message : "Échec d'exécution",
        nodes: get().nodes.map((node) => ({
          ...node,
          data: { ...node.data, status: "idle" },
        })),
      });
    }
  },
}));
