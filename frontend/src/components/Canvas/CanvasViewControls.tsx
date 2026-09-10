import { MiniMap, useReactFlow } from "@xyflow/react";

type CanvasViewControlsProps = {
	locked: boolean;
	onToggleLock: () => void;
};

export function CanvasViewControls({
	locked,
	onToggleLock,
}: CanvasViewControlsProps) {
	const { zoomIn, zoomOut, fitView } = useReactFlow();

	return (
		<div className="canvas-view-controls">
			<div className="canvas-view-controls__tools">
				<button type="button" title="Zoom in" onClick={() => zoomIn()}>
					+
				</button>
				<button type="button" title="Zoom out" onClick={() => zoomOut()}>
					−
				</button>
				<button
					type="button"
					title="Fit view"
					onClick={() => fitView({ padding: 0.2 })}
				>
					⤢
				</button>
				<button
					type="button"
					title={locked ? "Unlock canvas" : "Lock canvas"}
					className={locked ? "is-active" : ""}
					onClick={onToggleLock}
				>
					{locked ? "🔒" : "🔓"}
				</button>
			</div>
			<MiniMap
				pannable
				zoomable
				className="canvas-minimap"
				maskColor="rgba(20, 20, 22, 0.72)"
				nodeColor={() => "#5b5e66"}
			/>
		</div>
	);
}
