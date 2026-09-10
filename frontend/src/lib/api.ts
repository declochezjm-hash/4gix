export type NodeCategory = "Reader" | "Transformer" | "Writer";

export type SchemaProperty = {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  format?: string;
  minimum?: number;
  maximum?: number;
};

export type NodeSchema = {
  title?: string;
  description?: string;
  type?: string;
  properties?: Record<string, SchemaProperty>;
  required?: string[];
};

export type CatalogNode = {
  node_type: string;
  category: NodeCategory;
  is_spatial: boolean;
  label: string;
  description: string;
  schema: NodeSchema;
};

export type NodeSnapshot = {
  node_id: string;
  node_type: string;
  status: "success" | "error" | string;
  duration_ms: number;
  metadata: Record<string, unknown>;
  preview: unknown;
  error?: string | null;
};

export type ExecutionResult = {
  execution_id: string;
  status: string;
  snapshots: NodeSnapshot[];
  error?: string | null;
  duration_ms: number;
  node_count: number;
};

export type FlowNodeData = {
  label: string;
  nodeType: string;
  category: NodeCategory;
  isSpatial: boolean;
  params: Record<string, unknown>;
  schema?: NodeSchema;
  status?: "idle" | "running" | "success" | "error";
};

const API_BASE = import.meta.env.VITE_API_URL || "";

export async function fetchCatalog(): Promise<{
  count: number;
  nodes: CatalogNode[];
  by_category: Record<string, CatalogNode[]>;
}> {
  const response = await fetch(`${API_BASE}/api/nodes`);
  if (!response.ok) {
    throw new Error("Impossible de charger le catalogue de nœuds.");
  }
  return response.json();
}

export async function executeGraph(payload: {
  nodes: unknown[];
  edges: unknown[];
  name?: string;
}): Promise<ExecutionResult> {
  const response = await fetch(`${API_BASE}/api/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail || "Échec d'exécution du DAG.");
  }
  return body;
}

export function healthUrl(): string {
  return `${API_BASE}/health`;
}
