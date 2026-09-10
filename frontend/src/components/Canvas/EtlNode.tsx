import { Handle, type NodeProps, Position } from "@xyflow/react";
import type { FlowNodeData } from "../../lib/api";

const CATEGORY_ACCENT: Record<string, string> = {
	Reader: "#2aa198",
	Transformer: "#b58900",
	Writer: "#dc322f",
};

const HANDLE_LABEL: Record<string, string> = {
	input: "In",
	input_a: "A",
	input_b: "B",
};

export function EtlNode({ data, selected }: NodeProps) {
	const payload = data as FlowNodeData;
	const accent = CATEGORY_ACCENT[payload.category] || "#268bd2";
	const handles = payload.inputHandles?.length
		? payload.inputHandles
		: ["input"];
	const multi = handles.length > 1;
	const status = payload.status || "idle";
	const failed = status === "FAILED" || status === "error";
	const done = status === "COMPLETED" || status === "success";
	const running = status === "RUNNING" || status === "running";

	return (
		<div
			className={`etl-node etl-node--${status.toLowerCase()} ${selected ? "is-selected" : ""} ${running ? "is-running" : ""}`}
		>
			{handles.map((handleId, index) => (
				<Handle
					key={handleId}
					type="target"
					position={Position.Left}
					id={handleId}
					style={
						multi
							? { top: `${((index + 1) / (handles.length + 1)) * 100}%` }
							: undefined
					}
				/>
			))}
			{multi
				? handles.map((handleId, index) => (
						<span
							key={`${handleId}-label`}
							className="etl-node__handle-label"
							style={{ top: `${((index + 1) / (handles.length + 1)) * 100}%` }}
						>
							{HANDLE_LABEL[handleId] || handleId}
						</span>
					))
				: null}
			<div className="etl-node__bar" style={{ background: accent }} />
			<div className="etl-node__body">
				<span className="etl-node__cat">{payload.category}</span>
				<strong>{payload.label}</strong>
				<span className="etl-node__type">{payload.nodeType}</span>
				<div className="etl-node__badges">
					{payload.isSpatial ? (
						<span className="etl-node__badge">SIG</span>
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
			<Handle type="source" position={Position.Right} id="output" />
		</div>
	);
}
