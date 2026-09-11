import {
	Background,
	BackgroundVariant,
	ConnectionLineType,
	type Edge,
	type FinalConnectionState,
	type NodeTypes,
	ReactFlow,
	ReactFlowProvider,
	useReactFlow,
} from "@xyflow/react";
import {
	type DragEvent,
	useCallback,
	useEffect,
	useMemo,
	useState,
} from "react";
import { canvasDotsColor, readColorTheme } from "../../lib/theme";
import "@xyflow/react/dist/style.css";

import type { CatalogNode } from "../../lib/api";
import { isFmwFilename, isSpatialDataFilename } from "../../lib/api";
import { useDagStore } from "../../store/dagStore";
import { CanvasPageNav } from "./CanvasPageNav";
import { CanvasViewControls } from "./CanvasViewControls";
import { EdgeContextMenu } from "./EdgeContextMenu";
import { EtlNode } from "./EtlNode";
import { NodeContextMenu } from "./NodeContextMenu";

const nodeTypes = { etl: EtlNode } as NodeTypes;

const FIT_VIEW_OPTIONS = {
	padding: 0.14,
	minZoom: 0.02,
	maxZoom: 1.2,
	duration: 280,
} as const;

function CanvasViewportSync() {
	const nodes = useDagStore((s) => s.nodes);
	const viewportFitRequest = useDagStore((s) => s.viewportFitRequest);
	const canvasPaginationEnabled = useDagStore((s) => s.canvasPaginationEnabled);
	const canvasPages = useDagStore((s) => s.canvasPages);
	const canvasPageIndex = useDagStore((s) => s.canvasPageIndex);
	const { fitView } = useReactFlow();

	useEffect(() => {
		if (!nodes.length) return;
		const timer = window.setTimeout(() => {
			const pageIds = canvasPages[canvasPageIndex];
			if (canvasPaginationEnabled && pageIds?.length) {
				const visible = new Set(pageIds);
				void fitView({
					...FIT_VIEW_OPTIONS,
					nodes: nodes.filter((node) => visible.has(node.id)),
				});
				return;
			}
			void fitView(FIT_VIEW_OPTIONS);
		}, 60);
		return () => window.clearTimeout(timer);
	}, [
		viewportFitRequest,
		canvasPageIndex,
		canvasPaginationEnabled,
		canvasPages,
		nodes,
		fitView,
	]);

	return null;
}

function FlowCanvasInner() {
	const nodes = useDagStore((s) => s.nodes);
	const edges = useDagStore((s) => s.edges);
	const canvasLocked = useDagStore((s) => s.canvasLocked);
	const onNodesChange = useDagStore((s) => s.onNodesChange);
	const onEdgesChange = useDagStore((s) => s.onEdgesChange);
	const onConnect = useDagStore((s) => s.onConnect);
	const onReconnect = useDagStore((s) => s.onReconnect);
	const removeEdge = useDagStore((s) => s.removeEdge);
	const edgePathStyle = useDagStore((s) => s.edgePathStyle);
	const selectNode = useDagStore((s) => s.selectNode);
	const openInspector = useDagStore((s) => s.openInspector);
	const openNodePanel = useDagStore((s) => s.openNodePanel);
	const closeNodePanel = useDagStore((s) => s.closeNodePanel);
	const closeContextMenu = useDagStore((s) => s.closeContextMenu);
	const addCatalogNode = useDagStore((s) => s.addCatalogNode);
	const importLocalWorkflowFile = useDagStore((s) => s.importLocalWorkflowFile);
	const importDataFileFromDrop = useDagStore((s) => s.importDataFileFromDrop);
	const setCanvasLocked = useDagStore((s) => s.setCanvasLocked);
	const canvasPaginationEnabled = useDagStore((s) => s.canvasPaginationEnabled);
	const canvasPages = useDagStore((s) => s.canvasPages);
	const canvasPageIndex = useDagStore((s) => s.canvasPageIndex);

	const visibleIdSet = useMemo(() => {
		if (!canvasPaginationEnabled || !canvasPages.length) return null;
		return new Set(canvasPages[canvasPageIndex] ?? []);
	}, [canvasPaginationEnabled, canvasPages, canvasPageIndex]);

	const displayNodes = useMemo(
		() =>
			nodes.map((node) => ({
				...node,
				hidden: visibleIdSet ? !visibleIdSet.has(node.id) : false,
			})),
		[nodes, visibleIdSet],
	);

	const displayEdges = useMemo(
		() =>
			edges.map((edge) => {
				const hidden =
					visibleIdSet &&
					(!visibleIdSet.has(edge.source) || !visibleIdSet.has(edge.target));
				return {
					...edge,
					hidden: Boolean(hidden),
					style: {
						...(edge.style || {}),
						stroke: "#9aa3af",
						strokeWidth: canvasPaginationEnabled ? 2.75 : 2,
					},
				};
			}),
		[edges, visibleIdSet, canvasPaginationEnabled],
	);

	const [edgeMenu, setEdgeMenu] = useState<{
		edgeId: string;
		x: number;
		y: number;
	} | null>(null);
	const [dotColor, setDotColor] = useState(() =>
		canvasDotsColor(readColorTheme()),
	);

	useEffect(() => {
		const syncDots = () => setDotColor(canvasDotsColor(readColorTheme()));
		syncDots();
		const observer = new MutationObserver(syncDots);
		observer.observe(document.documentElement, {
			attributes: true,
			attributeFilter: ["data-theme"],
		});
		return () => observer.disconnect();
	}, []);

	const connectionLineType = useMemo(() => {
		if (edgePathStyle === "step") return ConnectionLineType.Step;
		if (edgePathStyle === "smoothstep") return ConnectionLineType.SmoothStep;
		return ConnectionLineType.Bezier;
	}, [edgePathStyle]);

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
			type: edgePathStyle,
			animated: false,
			interactionWidth: 22,
			style: { stroke: "#8a8d93", strokeWidth: 2 },
		}),
		[edgePathStyle],
	);

	const onReconnectEnd = useCallback(
		(
			_event: MouseEvent | TouchEvent,
			edge: Edge,
			_handleType: string,
			connectionState: FinalConnectionState,
		) => {
			if (!connectionState.isValid) {
				removeEdge(edge.id);
			}
		},
		[removeEdge],
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
				nodes={displayNodes}
				edges={displayEdges}
				onNodesChange={onNodesChange}
				onEdgesChange={onEdgesChange}
				onConnect={onConnect}
				onReconnect={onReconnect}
				onReconnectEnd={onReconnectEnd}
				onConnectEnd={onConnectEnd}
				connectionLineType={connectionLineType}
				connectionRadius={28}
				reconnectRadius={22}
				deleteKeyCode={["Delete", "Backspace"]}
				edgesFocusable
				edgesReconnectable={!canvasLocked}
				onEdgeContextMenu={(event, edge) => {
					event.preventDefault();
					setEdgeMenu({
						edgeId: edge.id,
						x: event.clientX,
						y: event.clientY,
					});
					closeContextMenu();
				}}
				onNodeClick={(_, node) => {
					selectNode(node.id);
					closeContextMenu();
					setEdgeMenu(null);
				}}
				onNodeDoubleClick={(_, node) => openInspector(node.id)}
				onPaneClick={() => {
					selectNode(null);
					closeNodePanel();
					closeContextMenu();
					setEdgeMenu(null);
				}}
				nodeTypes={nodeTypes}
				nodesDraggable={!canvasLocked}
				nodesConnectable={!canvasLocked}
				elementsSelectable={!canvasLocked}
				minZoom={0.02}
				maxZoom={2}
				elevateEdgesOnSelect
				elevateNodesOnSelect
				defaultEdgeOptions={defaultEdgeOptions}
				connectionLineStyle={{ stroke: "#8a8d93", strokeWidth: 2 }}
			>
				<CanvasViewportSync />
				<Background
					id="n8n-dots"
					variant={BackgroundVariant.Dots}
					gap={22}
					size={1.15}
					color={dotColor}
				/>
				<CanvasViewControls
					locked={canvasLocked}
					onToggleLock={() => setCanvasLocked(!canvasLocked)}
				/>
			</ReactFlow>
			{edgeMenu ? (
				<EdgeContextMenu
					edgeId={edgeMenu.edgeId}
					x={edgeMenu.x}
					y={edgeMenu.y}
					onClose={() => setEdgeMenu(null)}
				/>
			) : null}
			<button
				type="button"
				className="canvas-plus"
				aria-label="Ajouter un nœud"
				title="Ajouter un nœud"
				onClick={() => openNodePanel(null)}
			>
				+
			</button>
			<CanvasPageNav />
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
