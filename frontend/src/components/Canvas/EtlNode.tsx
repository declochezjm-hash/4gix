import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { FlowNodeData } from "../../lib/api";

const CATEGORY_ACCENT: Record<string, string> = {
  Reader: "#2aa198",
  Transformer: "#b58900",
  Writer: "#dc322f",
};

export function EtlNode({ data, selected }: NodeProps) {
  const payload = data as FlowNodeData;
  const accent = CATEGORY_ACCENT[payload.category] || "#268bd2";
  return (
    <div className={`etl-node etl-node--${payload.status || "idle"} ${selected ? "is-selected" : ""}`}>
      <Handle type="target" position={Position.Left} id="input" />
      <div className="etl-node__bar" style={{ background: accent }} />
      <div className="etl-node__body">
        <span className="etl-node__cat">{payload.category}</span>
        <strong>{payload.label}</strong>
        <span className="etl-node__type">{payload.nodeType}</span>
        {payload.isSpatial ? <span className="etl-node__badge">SIG</span> : null}
      </div>
      <Handle type="source" position={Position.Right} id="output" />
    </div>
  );
}
