import { useDagStore } from "../../store/dagStore";
import { DataPane } from "./DataPane";

export function InputWindow() {
	const selectedNodeId = useDagStore((s) => s.selectedNodeId);
	const snapshots = useDagStore((s) => s.snapshots);
	const snapshot = selectedNodeId ? snapshots[selectedNodeId] : undefined;

	return (
		<DataPane
			title="Input"
			subtitle="Snapshot d'entrée (nœuds parents)"
			data={snapshot?.input_snapshot ?? null}
			empty="Aucun snapshot d'entrée. Exécutez le DAG puis cliquez un nœud."
			accent="#268bd2"
		/>
	);
}
