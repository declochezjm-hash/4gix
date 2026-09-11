import { useDagStore } from "../../store/dagStore";
import { DataPane } from "./DataPane";

export function OutputWindow() {
	const selectedNodeId = useDagStore((s) => s.selectedNodeId);
	const snapshots = useDagStore((s) => s.snapshots);
	const snapshot = selectedNodeId ? snapshots[selectedNodeId] : undefined;
	const data = snapshot?.output_snapshot ?? snapshot?.preview ?? null;

	return (
		<DataPane
			title="OUTPUT"
			subtitle={
				snapshot
					? `${snapshot.status} · ${Math.round(snapshot.duration_ms || 0)} ms`
					: "Entités résultantes · MapLibre / Deck.gl 3D"
			}
			data={data}
			empty="Aucune sortie. Execute Node pour inspecter le type d'entité, les attributs et la géométrie."
			accent="#22C55E"
			executionStatus={snapshot?.status}
			dataKey={selectedNodeId ?? undefined}
		/>
	);
}
