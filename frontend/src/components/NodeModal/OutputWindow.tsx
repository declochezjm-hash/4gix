import { useDagStore } from "../../store/dagStore";
import { DataPane } from "./DataPane";

export function OutputWindow() {
	const selectedNodeId = useDagStore((s) => s.selectedNodeId);
	const snapshots = useDagStore((s) => s.snapshots);
	const snapshot = selectedNodeId ? snapshots[selectedNodeId] : undefined;
	const data = snapshot?.output_snapshot ?? snapshot?.preview ?? null;

	return (
		<DataPane
			title="Output"
			subtitle={
				snapshot
					? `${snapshot.status} · ${Math.round(snapshot.duration_ms || 0)} ms`
					: "Snapshot Recflow après exécution"
			}
			data={data}
			empty="Aucun snapshot de sortie. Exécutez le graphe pour inspecter le résultat."
			accent="#2aa198"
		/>
	);
}
