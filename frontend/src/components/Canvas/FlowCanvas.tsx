import { useCallback, useMemo, type DragEvent } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useDagStore } from "../../store/dagStore";
import type { CatalogNode } from "../../lib/api";
import { EtlNode } from "./EtlNode";

const nodeTypes = { etl: EtlNode } as NodeTypes;

export function FlowCanvas() {
  const nodes = useDagStore((s) => s.nodes);
  const edges = useDagStore((s) => s.edges);
  const onNodesChange = useDagStore((s) => s.onNodesChange);
  const onEdgesChange = useDagStore((s) => s.onEdgesChange);
  const onConnect = useDagStore((s) => s.onConnect);
  const selectNode = useDagStore((s) => s.selectNode);
  const addCatalogNode = useDagStore((s) => s.addCatalogNode);

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData("application/4gix-node");
      if (!raw) return;
      const entry = JSON.parse(raw) as CatalogNode;
      const bounds = (event.target as HTMLElement).closest(".canvas-shell")?.getBoundingClientRect();
      const position = {
        x: event.clientX - (bounds?.left || 0) - 80,
        y: event.clientY - (bounds?.top || 0) - 24,
      };
      addCatalogNode(entry, position);
    },
    [addCatalogNode]
  );

  const defaultEdgeOptions = useMemo(
    () => ({ type: "smoothstep" as const, animated: true }),
    []
  );

  return (
    <div
      className="canvas-shell"
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => selectNode(node.id)}
        onPaneClick={() => selectNode(null)}
        nodeTypes={nodeTypes}
        fitView
        defaultEdgeOptions={defaultEdgeOptions}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#1d3a3a" />
        <MiniMap
          pannable
          zoomable
          maskColor="rgba(7, 22, 22, 0.7)"
          nodeColor={() => "#2aa198"}
        />
        <Controls />
      </ReactFlow>
    </div>
  );
}
