import { Handle, type NodeProps, Position } from "@xyflow/react";
import type { FlowNodeData } from "../../lib/api";

const CATEGORY_ACCENT: Record<string, string> = {
	Reader: "#2aa198",
	Transformer: "#b58900",
	Writer: "#dc322f",
};

const HANDLE_LABEL: Record<string, string> = {
	input: "Input",
	input_a: "A",
	input_b: "B",
	output: "Output",
	passed: "Passed",
	failed: "Failed",
	rejected: "Rejected",
	unique: "Unique",
	duplicate: "Duplicate",
	merged: "Merged",
	unmerged_request: "Unmerged_Request",
	unmerged_supplier: "Unmerged_Supplier",
	inside: "Inside",
	outside: "Outside",
	point: "Point",
	linestring: "Line",
	polygon: "Polygon",
	multipolygon: "MultiPolygon",
	null: "Null",
	else: "Else",
	clipper: "Clipper",
	request: "Request",
	supplier: "Supplier",
	base: "Base",
	candidates: "Candidates",
	related: "Related",
	unrelated: "Unrelated",
	output1: "OUTPUT1",
	output2: "OUTPUT2",
	output3: "OUTPUT3",
};

function labelOf(handleId: string): string {
	return HANDLE_LABEL[handleId] || handleId;
}

export function EtlNode({ data, selected }: NodeProps) {
	const payload = data as FlowNodeData;
	const accent = CATEGORY_ACCENT[payload.category] || "#268bd2";
	const inHandles = payload.inputHandles?.length
		? payload.inputHandles
		: ["input"];
	const outHandles = payload.outputHandles?.length
		? payload.outputHandles
		: ["output"];
	const multiIn = inHandles.length > 1;
	const multiOut = outHandles.length > 1;
	const status = payload.status || "idle";
	const failed = status === "FAILED" || status === "error";
	const done = status === "COMPLETED" || status === "success";
	const running = status === "RUNNING" || status === "running";
	const rows = Math.max(inHandles.length, outHandles.length);
	const minHeight = Math.max(86, rows * 22 + 48);

	return (
		<div
			className={`etl-node etl-node--${status.toLowerCase()} ${selected ? "is-selected" : ""} ${running ? "is-running" : ""}`}
			style={{ minHeight }}
		>
			{inHandles.map((handleId, index) => (
				<Handle
					key={`in-${handleId}`}
					type="target"
					position={Position.Left}
					id={handleId}
					style={{ top: `${((index + 1) / (inHandles.length + 1)) * 100}%` }}
				/>
			))}
			{(multiIn ? inHandles : []).map((handleId, index) => (
				<span
					key={`in-label-${handleId}`}
					className="etl-node__handle-label"
					style={{ top: `${((index + 1) / (inHandles.length + 1)) * 100}%` }}
				>
					{labelOf(handleId)}
				</span>
			))}
			<div className="etl-node__bar" style={{ background: accent }} />
			<div className="etl-node__body">
				<span className="etl-node__cat">{payload.category}</span>
				<strong>{payload.label}</strong>
				<span className="etl-node__type">{payload.nodeType}</span>
				<div className="etl-node__badges">
					{payload.isSpatial ? (
						<span className="etl-node__badge">SIG</span>
					) : null}
					{multiOut ? (
						<span className="etl-node__badge">{outHandles.length} ports</span>
					) : null}
					{running ? (
						<span className="etl-node__badge etl-node__badge--run">
							RUNNING
						</span>
					) : null}
					{done ? (
						<span className="etl-node__badge etl-node__badge--ok">
							{Math.round(payload.durationMs || 0)} ms
						</span>
					) : null}
					{failed ? (
						<span
							className="etl-node__badge etl-node__badge--err"
							title={payload.error || ""}
						>
							FAILED
						</span>
					) : null}
				</div>
				{failed && payload.error ? (
					<span className="etl-node__error">{payload.error}</span>
				) : null}
			</div>
			{outHandles.map((handleId, index) => (
				<Handle
					key={`out-${handleId}`}
					type="source"
					position={Position.Right}
					id={handleId}
					style={{ top: `${((index + 1) / (outHandles.length + 1)) * 100}%` }}
				/>
			))}
			{(multiOut ? outHandles : []).map((handleId, index) => (
				<span
					key={`out-label-${handleId}`}
					className="etl-node__handle-label etl-node__handle-label--out"
					style={{ top: `${((index + 1) / (outHandles.length + 1)) * 100}%` }}
				>
					{labelOf(handleId)}
				</span>
			))}
		</div>
	);
}
