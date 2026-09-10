import { useMemo, useState } from "react";
import {
	asFeatureCollection,
	asRasterPreview,
	crsFromCollection,
	inspectFeature,
	listPorts,
	pickPort,
	tableRowsFromData,
} from "../../lib/geo";
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
	const raster = asRasterPreview(data);
	const ports = listPorts(data);
	const [tab, setTab] = useState<"table" | "map" | "raster" | "fme">(
		raster ? "raster" : "fme",
	);
	const [port, setPort] = useState<string>("");
	const [filter, setFilter] = useState("");
	const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
	const mapView = useDagStore((s) => s.mapView);
	const setMapView = useDagStore((s) => s.setMapView);
	const activePort = port && ports.includes(port) ? port : ports[0] || "";
	const scoped = ports.length ? pickPort(data, activePort) : data;
	const geojson = asFeatureCollection(scoped);
	const table = tableRowsFromData(scoped);
	const hasGeometry = Boolean(
		geojson?.features.some((feature) => feature.geometry),
	);
	const selectedFeature =
		selectedIndex != null ? geojson?.features[selectedIndex] : undefined;
	const inspect = inspectFeature(selectedFeature, crsFromCollection(geojson));
	const filteredRows = useMemo(() => {
		const query = filter.trim().toLowerCase();
		if (!query) {
			return table.rows.map((row, index) => ({ row, index }));
		}
		return table.rows
			.map((row, index) => ({ row, index }))
			.filter(({ row }) =>
				table.columns.some((column) =>
					String(row[column] ?? "")
						.toLowerCase()
						.includes(query),
				),
			);
	}, [filter, table.columns, table.rows]);

	return (
		<section className="inspector-pane">
			<header>
				<h3>{title}</h3>
				<p>{subtitle}</p>
				{ports.length ? (
					<label className="port-select">
						Port
						<select
							value={activePort}
							onChange={(event) => {
								setPort(event.target.value);
								setSelectedIndex(null);
							}}
						>
							{ports.map((name) => (
								<option key={name} value={name}>
									{name}
								</option>
							))}
						</select>
					</label>
				) : null}
				<div className="pane-tabs" role="tablist">
					<button
						type="button"
						className={tab === "fme" ? "is-active" : ""}
						onClick={() => setTab("fme")}
					>
						FME Data Inspector
					</button>
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
					<button
						type="button"
						className={tab === "raster" ? "is-active" : ""}
						onClick={() => setTab("raster")}
					>
						Raster
					</button>
				</div>
			</header>
			{data == null ? (
				<div className="empty">{empty}</div>
			) : tab === "raster" ? (
				raster ? (
					<figure className="raster-preview">
						<img src={raster.src} alt="Prévisualisation raster" />
						<figcaption>
							{raster.path || "GeoTIFF"}
							{raster.width && raster.height
								? ` · ${raster.width}×${raster.height}`
								: ""}
							{raster.crs ? ` · ${raster.crs}` : ""}
							{raster.stats
								? ` · min ${raster.stats.min} / max ${raster.stats.max}`
								: ""}
						</figcaption>
					</figure>
				) : (
					<div className="empty">
						Pas de prévisualisation raster (PNG Base64) dans ce snapshot.
					</div>
				)
			) : tab === "map" ? (
				hasGeometry ? (
					<div className="map-embed map-embed--tall">
						<MapViewer
							geojson={geojson}
							view={mapView}
							onViewChange={setMapView}
							accent={accent}
							selectedIndex={selectedIndex}
						/>
					</div>
				) : (
					<div className="empty">Pas de géométrie GeoJSON à afficher.</div>
				)
			) : tab === "fme" ? (
				<div className="fme-inspector">
					<dl className="fme-structure">
						<div>
							<dt>Type de géométrie</dt>
							<dd>{inspect.geomType}</dd>
						</div>
						<div>
							<dt>Bounding Box</dt>
							<dd>
								{inspect.bbox
									? `[${inspect.bbox.map((n) => n.toFixed(5)).join(", ")}]`
									: "—"}
							</dd>
						</div>
						<div>
							<dt>Sommets</dt>
							<dd>{inspect.vertices}</dd>
						</div>
						<div>
							<dt>EPSG</dt>
							<dd>{inspect.epsg}</dd>
						</div>
						<div>
							<dt>Entités</dt>
							<dd>{geojson?.features.length ?? table.rows.length}</dd>
						</div>
					</dl>
					{hasGeometry ? (
						<div className="map-embed">
							<MapViewer
								geojson={geojson}
								view={mapView}
								onViewChange={setMapView}
								accent={accent}
								selectedIndex={selectedIndex}
							/>
						</div>
					) : null}
					<input
						className="fme-filter"
						placeholder="Filtrer les attributs…"
						value={filter}
						onChange={(event) => setFilter(event.target.value)}
					/>
					{filteredRows.length ? (
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
									{filteredRows.slice(0, 80).map(({ row, index }) => (
										<tr
											key={index}
											className={
												selectedIndex === index ? "is-selected-feature" : ""
											}
											onClick={() => setSelectedIndex(index)}
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
						<div className="empty">Aucune entité à inspecter.</div>
					)}
				</div>
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
							{table.rows.slice(0, 80).map((row, index) => (
								<tr
									key={table.columns
										.map((column) => String(row[column] ?? ""))
										.join("\0")}
									className={
										selectedIndex === index ? "is-selected-feature" : ""
									}
									onClick={() => setSelectedIndex(index)}
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
				<pre>{JSON.stringify(stripBase64(data), null, 2)}</pre>
			)}
		</section>
	);
}

function formatCell(value: unknown): string {
	if (value === null || value === undefined) return "";
	if (typeof value === "object") return JSON.stringify(value);
	return String(value);
}

function stripBase64(value: unknown): unknown {
	if (!value || typeof value !== "object") return value;
	if (Array.isArray(value)) return value;
	const record = { ...(value as Record<string, unknown>) };
	if (typeof record.preview_png_base64 === "string") {
		record.preview_png_base64 = `[png ${record.preview_png_base64.length} chars]`;
	}
	if (record.data && typeof record.data === "object") {
		record.data = stripBase64(record.data);
	}
	return record;
}
