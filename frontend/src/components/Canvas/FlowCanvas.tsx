import {
	Background,
	BackgroundVariant,
	type NodeTypes,
	ReactFlow,
	ReactFlowProvider,
} from "@xyflow/react";
import { type DragEvent, useCallback, useMemo } from "react";
import "@xyflow/react/dist/style.css";

import type { CatalogNode } from "../../lib/api";
import { isFmwFilename, isSpatialDataFilename } from "../../lib/api";
import { useDagStore } from "../../store/dagStore";
import { CanvasViewControls } from "./CanvasViewControls";
import { EtlNode } from "./EtlNode";
import { NodeContextMenu } from "./NodeContextMenu";

const nodeTypes = { etl: EtlNode } as NodeTypes;

function FlowCanvasInner() {
	const nodes = useDagStore((s) => s.nodes);
	const edges = useDagStore((s) => s.edges);
	const canvasLocked = useDagStore((s) => s.canvasLocked);
	const onNodesChange = useDagStore((s) => s.onNodesChange);
	const onEdgesChange = useDagStore((s) => s.onEdgesChange);
	const onConnect = useDagStore((s) => s.onConnect);
	const selectNode = useDagStore((s) => s.selectNode);
	const openInspector = useDagStore((s) => s.openInspector);
	const openNodePanel = useDagStore((s) => s.openNodePanel);
	const closeNodePanel = useDagStore((s) => s.closeNodePanel);
	const closeContextMenu = useDagStore((s) => s.closeContextMenu);
	const addCatalogNode = useDagStore((s) => s.addCatalogNode);
	const importLocalWorkflowFile = useDagStore((s) => s.importLocalWorkflowFile);
	const importDataFileFromDrop = useDagStore((s) => s.importDataFileFromDrop);
	const setCanvasLocked = useDagStore((s) => s.setCanvasLocked);

	const onDrop = useCallback(
		(event: DragEvent) => {
			event.preventDefault();
			const dropped = event.dataTransfer.files?.[0];
			if (dropped) {
				const lower = dropped.name.toLowerCase();
				if (isFmwFilename(dropped.name) || lower.endsWith(".json")) {
					void importLocalWorkflowFile(dropped);
					return;
				}
				if (isSpatialDataFilename(dropped.name)) {
					const bounds = (event.target as HTMLElement)
						.closest(".canvas-shell")
						?.getBoundingClientRect();
					const position = {
						x: event.clientX - (bounds?.left || 0) - 80,
						y: event.clientY - (bounds?.top || 0) - 24,
					};
					void importDataFileFromDrop(dropped, position);
					return;
				}
			}
			const raw = event.dataTransfer.getData("application/4gix-node");
			if (!raw) return;
			const entry = JSON.parse(raw) as CatalogNode;
			const bounds = (event.target as HTMLElement)
				.closest(".canvas-shell")
				?.getBoundingClientRect();
			const position = {
				x: event.clientX - (bounds?.left || 0) - 80,
				y: event.clientY - (bounds?.top || 0) - 24,
			};
			addCatalogNode(entry, position);
		},
		[addCatalogNode, importLocalWorkflowFile, importDataFileFromDrop],
	);

	const defaultEdgeOptions = useMemo(
		() => ({
			type: "default" as const,
			animated: false,
			style: { stroke: "#8a8d93", strokeWidth: 2 },
		}),
		[],
	);

	const onConnectEnd = useCallback(
		(event: MouseEvent | TouchEvent, state: Record<string, unknown>) => {
			const fromNode = state.fromNode as { id: string } | undefined;
			const fromHandle = state.fromHandle as
				| { id?: string | null; type?: string | null }
				| undefined;
			if (state.isValid) return;
			if (fromHandle?.type !== "source" || !fromNode) return;
			const target = event.target as HTMLElement | null;
			if (target?.closest(".n8n-panel")) return;
			openNodePanel({
				nodeId: fromNode.id,
				handleId: fromHandle.id || "output",
			});
		},
		[openNodePanel],
	);

	return (
		<div
			className="canvas-shell"
			role="application"
			aria-label="Canvas du workflow ETL"
			onDragOver={(event) => event.preventDefault()}
			onDrop={onDrop}
		>
			<ReactFlow
				nodes={nodes}
				edges={edges}
				onNodesChange={onNodesChange}
				onEdgesChange={onEdgesChange}
				onConnect={onConnect}
				onConnectEnd={onConnectEnd}
				onNodeClick={(_, node) => {
					selectNode(node.id);
					closeContextMenu();
				}}
				onNodeDoubleClick={(_, node) => openInspector(node.id)}
				onPaneClick={() => {
					selectNode(null);
					closeNodePanel();
					closeContextMenu();
				}}
				nodeTypes={nodeTypes}
				nodesDraggable={!canvasLocked}
				nodesConnectable={!canvasLocked}
				elementsSelectable={!canvasLocked}
				fitView
				defaultEdgeOptions={defaultEdgeOptions}
				connectionLineStyle={{ stroke: "#8a8d93", strokeWidth: 2 }}
			>
				<Background
					id="n8n-dots"
					variant={BackgroundVariant.Dots}
					gap={22}
					size={1.15}
					color="#3a3b40"
				/>
				<CanvasViewControls
					locked={canvasLocked}
					onToggleLock={() => setCanvasLocked(!canvasLocked)}
				/>
			</ReactFlow>
			<button
				type="button"
				className="canvas-plus"
				aria-label="Ajouter un nœud"
				title="Ajouter un nœud"
				onClick={() => openNodePanel(null)}
			>
				+
			</button>
			<NodeContextMenu />
		</div>
	);
}

export function FlowCanvas() {
	return (
		<ReactFlowProvider>
			<FlowCanvasInner />
		</ReactFlowProvider>
	);
}
