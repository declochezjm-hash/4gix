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
	output_handles?: string[];
	fme_group?: string;
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
	outputHandles?: string[];
	fmeGroup?: string;
	notes?: string;
	disabled?: boolean;
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

export type FmwImportResult = {
	name: string;
	format: string;
	source: string;
	filename?: string;
	warnings: string[];
	definition: {
		nodes: unknown[];
		edges: unknown[];
	};
};

export type DataUploadResult = {
	filename: string;
	filepath: string;
	workspace_path?: string;
	detected_type: "shapefile" | "geojson" | "geotiff";
	suggested_node?: {
		node_type: string;
		label: string;
		params: Record<string, unknown>;
	};
};

export type ShapefileZipImportResult = {
	format: string;
	source: string;
	filename: string;
	label: string;
	geojson: Record<string, unknown>;
	metadata: Record<string, unknown>;
	suggested_node: {
		node_type: string;
		label: string;
		params: Record<string, unknown>;
	};
	validation?: {
		shapefile_sets: number;
		components_detected: string[];
	};
};

export function formatApiErrorDetail(payload: unknown, fallback: string): string {
	if (!payload || typeof payload !== "object") return fallback;
	const detail = (payload as { detail?: unknown }).detail;
	if (typeof detail === "string") return detail;
	if (Array.isArray(detail)) {
		return detail
			.map((item) =>
				typeof item === "object" && item && "msg" in item
					? String((item as { msg: string }).msg)
					: String(item),
			)
			.join(" ");
	}
	return fallback;
}

export type FmeEngineRunResult = {
	status: string;
	exit_code: number;
	log: string;
	name?: string;
	source?: string;
};

export async function executeFmwFile(file: File): Promise<FmeEngineRunResult> {
	const body = new FormData();
	body.append("file", file);
	const response = await fetch(`${API_BASE}/api/v1/workflows/execute-fmw`, {
		method: "POST",
		body,
	});
	const payload = await response.json();
	if (!response.ok) {
		throw new Error(formatApiErrorDetail(payload, "Exécution FME impossible."));
	}
	return payload as FmeEngineRunResult;
}

export async function importFmwFile(file: File): Promise<FmwImportResult> {
	const body = new FormData();
	body.append("file", file);
	const response = await fetch(`${API_BASE}/api/v1/workflows/import-fmw`, {
		method: "POST",
		body,
	});
	const payload = await response.json();
	if (!response.ok) {
		throw new Error(
			formatApiErrorDetail(payload, "Import FME impossible."),
		);
	}
	return payload;
}

export function isShapefileZipFilename(name: string): boolean {
	return name.toLowerCase().endsWith(".zip");
}

export function isGeoJsonDataFilename(name: string): boolean {
	return name.toLowerCase().endsWith(".geojson");
}

export function isGeoTiffDataFilename(name: string): boolean {
	const lower = name.toLowerCase();
	return (
		lower.endsWith(".tif") ||
		lower.endsWith(".tiff") ||
		lower.endsWith(".geotiff")
	);
}

export function isSpatialDataFilename(name: string): boolean {
	return (
		isShapefileZipFilename(name) ||
		isGeoJsonDataFilename(name) ||
		isGeoTiffDataFilename(name)
	);
}

export async function uploadDataFile(file: File): Promise<DataUploadResult> {
	const body = new FormData();
	body.append("file", file);
	const response = await fetch(`${API_BASE}/api/v1/upload`, {
		method: "POST",
		body,
	});
	const payload = await response.json();
	if (!response.ok) {
		throw new Error(
			formatApiErrorDetail(payload, "Téléversement de données impossible."),
		);
	}
	return payload as DataUploadResult;
}

/** Détection légère côté navigateur (signature PK + présence .shp/.dbf/.shx dans les noms). */
export async function zipLooksLikeShapefile(file: File): Promise<boolean> {
	if (!isShapefileZipFilename(file.name)) return false;
	const head = new Uint8Array(await file.slice(0, 4).arrayBuffer());
	if (head[0] !== 0x50 || head[1] !== 0x4b) return false;
	try {
		const buffer = await file.arrayBuffer();
		const text = new TextDecoder("latin1").decode(buffer);
		const lower = text.toLowerCase();
		return lower.includes(".shp") && lower.includes(".dbf") && lower.includes(".shx");
	} catch {
		return true;
	}
}

export async function importShapefileZip(
	file: File,
): Promise<ShapefileZipImportResult> {
	const body = new FormData();
	body.append("file", file);
	const response = await fetch(
		`${API_BASE}/api/v1/datasets/import-shapefile-zip`,
		{
			method: "POST",
			body,
		},
	);
	const payload = await response.json();
	if (!response.ok) {
		throw new Error(
			formatApiErrorDetail(payload, "Import Shapefile (.zip) impossible."),
		);
	}
	return payload as ShapefileZipImportResult;
}

export function exportFmwUrl(workflowId: string): string {
	return `${API_BASE}/api/v1/workflows/${workflowId}/export-fmw`;
}

export function isFmwFilename(name: string): boolean {
	const lower = name.toLowerCase();
	return lower.endsWith(".fmw") || lower.endsWith(".fmwt");
}

export async function downloadExportFmw(
	workflowId: string,
	filename: string,
): Promise<void> {
	const response = await fetch(exportFmwUrl(workflowId));
	if (!response.ok) {
		let detail = "Export FME impossible.";
		try {
			const payload = (await response.json()) as { detail?: string };
			if (payload.detail) detail = payload.detail;
		} catch {
			/* ignore */
		}
		throw new Error(detail);
	}
	const blob = await response.blob();
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement("a");
	anchor.href = url;
	anchor.download = filename.toLowerCase().endsWith(".fmw")
		? filename
		: `${filename}.fmw`;
	anchor.click();
	URL.revokeObjectURL(url);
}
