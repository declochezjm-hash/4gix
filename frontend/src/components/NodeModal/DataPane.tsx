import { useState } from "react";
import { asFeatureCollection, tableRowsFromData } from "../../lib/geo";
import { useDagStore } from "../../store/dagStore";
import { MapViewer } from "../MapViewer/MapViewer";

type DataPaneProps = {
	title: string;
	subtitle: string;
	data: unknown;
	empty: string;
	accent?: string;
};

export function DataPane({
	title,
	subtitle,
	data,
	empty,
	accent,
}: DataPaneProps) {
	const [tab, setTab] = useState<"table" | "map">("table");
	const mapView = useDagStore((s) => s.mapView);
	const setMapView = useDagStore((s) => s.setMapView);
	const geojson = asFeatureCollection(data);
	const table = tableRowsFromData(data);
	const hasGeometry = Boolean(
		geojson?.features.some((feature) => feature.geometry),
	);

	return (
		<section className="inspector-pane">
			<header>
				<h3>{title}</h3>
				<p>{subtitle}</p>
				<div className="pane-tabs" role="tablist">
					<button
						type="button"
						className={tab === "table" ? "is-active" : ""}
						onClick={() => setTab("table")}
					>
						Tableau / JSON
					</button>
					<button
						type="button"
						className={tab === "map" ? "is-active" : ""}
						onClick={() => setTab("map")}
					>
						Carte SIG
					</button>
				</div>
			</header>
			{data == null ? (
				<div className="empty">{empty}</div>
			) : tab === "map" ? (
				hasGeometry ? (
					<div className="map-embed map-embed--tall">
						<MapViewer
							geojson={geojson}
							view={mapView}
							onViewChange={setMapView}
							accent={accent}
						/>
					</div>
				) : (
					<div className="empty">Pas de géométrie GeoJSON à afficher.</div>
				)
			) : table.rows.length ? (
				<div className="table-wrap">
					<table>
						<thead>
							<tr>
								{table.columns.map((column) => (
									<th key={column}>{column}</th>
								))}
							</tr>
						</thead>
						<tbody>
							{table.rows.slice(0, 80).map((row) => (
								<tr
									key={table.columns
										.map((column) => String(row[column] ?? ""))
										.join("\0")}
								>
									{table.columns.map((column) => (
										<td key={column}>{formatCell(row[column])}</td>
									))}
								</tr>
							))}
						</tbody>
					</table>
				</div>
			) : (
				<pre>{JSON.stringify(data, null, 2)}</pre>
			)}
		</section>
	);
}

function formatCell(value: unknown): string {
	if (value === null || value === undefined) return "";
	if (typeof value === "object") return JSON.stringify(value);
	return String(value);
}
