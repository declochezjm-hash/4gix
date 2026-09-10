export type NodeCategory = "Reader" | "Transformer" | "Writer";

export type SchemaProperty = {
	type?: string;
	title?: string;
	description?: string;
	default?: unknown;
	enum?: string[];
	enumNames?: string[];
	format?: string;
	minimum?: number;
	maximum?: number;
	multipleOf?: number;
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
	input_handles?: string[];
};

export type NodeSnapshot = {
	node_id: string;
	node_type: string;
	status: "success" | "error" | "COMPLETED" | "FAILED" | "RUNNING" | string;
	duration_ms: number;
	metadata: Record<string, unknown>;
	preview: unknown;
	input_snapshot?: unknown;
	output_snapshot?: unknown;
	error?: string | null;
};

export type ExecutionResult = {
	execution_id: string;
	workflow_id?: string | null;
	status: string;
	snapshots: NodeSnapshot[];
	error?: string | null;
	duration_ms: number;
	node_count: number;
	logs?: string;
};

export type WorkflowRecord = {
	id: string;
	name: string;
	definition: {
		nodes?: unknown[];
		edges?: unknown[];
	};
	created_at?: string;
	updated_at?: string;
};

export type MapViewState = {
	longitude: number;
	latitude: number;
	zoom: number;
};

export type FlowNodeData = {
	label: string;
	nodeType: string;
	category: NodeCategory;
	isSpatial: boolean;
	params: Record<string, unknown>;
	schema?: NodeSchema;
	status?:
		| "idle"
		| "running"
		| "success"
		| "error"
		| "COMPLETED"
		| "FAILED"
		| "RUNNING";
	durationMs?: number;
	error?: string | null;
	inputHandles?: string[];
};

const API_BASE = import.meta.env.VITE_API_URL || "";

export function wsExecuteUrl(): string {
	const explicit = import.meta.env.VITE_WS_URL;
	if (explicit) {
		return `${explicit.replace(/\/$/, "")}/api/ws/execute`;
	}
	if (API_BASE) {
		return `${API_BASE.replace(/^http/, "ws").replace(/\/$/, "")}/api/ws/execute`;
	}
	const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
	return `${protocol}//${window.location.host}/api/ws/execute`;
}

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
	workflow_id?: string | null;
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

export async function fetchWorkflows(): Promise<{
	count: number;
	workflows: WorkflowRecord[];
}> {
	const response = await fetch(`${API_BASE}/api/workflows`);
	if (!response.ok) {
		throw new Error("Impossible de lister les workflows.");
	}
	return response.json();
}

export async function saveWorkflow(payload: {
	id?: string | null;
	name: string;
	definition: unknown;
}): Promise<WorkflowRecord> {
	const response = await fetch(`${API_BASE}/api/workflows`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(payload),
	});
	const body = await response.json();
	if (!response.ok) {
		throw new Error(body.detail || "Impossible d'enregistrer le workflow.");
	}
	return body;
}

export async function fetchNodeSnapshot(
	executionId: string,
	nodeId: string,
): Promise<{
	execution_id: string;
	node_id: string;
	input_snapshot: unknown;
	output_snapshot: unknown;
	execution_time_ms: number;
}> {
	const response = await fetch(
		`${API_BASE}/api/executions/${executionId}/snapshots/${nodeId}`,
	);
	if (!response.ok) {
		throw new Error("Snapshot introuvable.");
	}
	return response.json();
}

export function healthUrl(): string {
	return `${API_BASE}/health`;
}
