import type { FeatureCollection } from "geojson";
import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

import type { MapViewState } from "../../lib/api";
import {
	asFeatureCollection,
	type GeoJsonFeatureCollection,
} from "../../lib/geo";

type MapViewerProps = {
	geojson?: unknown;
	view?: MapViewState | null;
	onViewChange?: (view: MapViewState) => void;
	accent?: string;
};

const EMPTY: GeoJsonFeatureCollection = {
	type: "FeatureCollection",
	features: [],
};

function extendBounds(
	bounds: maplibregl.LngLatBounds,
	geom: { type: string; coordinates: unknown } | null | undefined,
) {
	if (!geom) return;
	const walk = (coords: unknown) => {
		if (!Array.isArray(coords)) return;
		if (typeof coords[0] === "number" && typeof coords[1] === "number") {
			bounds.extend([coords[0] as number, coords[1] as number]);
			return;
		}
		for (const item of coords) walk(item);
	};
	walk(geom.coordinates);
}

export function MapViewer({
	geojson,
	view,
	onViewChange,
	accent = "#2aa198",
}: MapViewerProps) {
	const containerRef = useRef<HTMLDivElement | null>(null);
	const mapRef = useRef<maplibregl.Map | null>(null);
	const applyingRef = useRef(false);
	const onViewChangeRef = useRef(onViewChange);
	onViewChangeRef.current = onViewChange;

	useEffect(() => {
		if (!containerRef.current || mapRef.current) return;
		const map = new maplibregl.Map({
			container: containerRef.current,
			style: {
				version: 8,
				sources: {
					osm: {
						type: "raster",
						tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
						tileSize: 256,
						attribution: "© OpenStreetMap",
					},
				},
				layers: [{ id: "osm", type: "raster", source: "osm" }],
			},
			center: [2.3, 46.5],
			zoom: 4.4,
		});
		map.addControl(
			new maplibregl.NavigationControl({ showCompass: false }),
			"top-right",
		);
		map.on("load", () => {
			map.addSource("preview", {
				type: "geojson",
				data: EMPTY as FeatureCollection,
			});
			map.addLayer({
				id: "preview-fill",
				type: "fill",
				source: "preview",
				paint: { "fill-color": accent, "fill-opacity": 0.28 },
				filter: ["==", "$type", "Polygon"],
			});
			map.addLayer({
				id: "preview-line",
				type: "line",
				source: "preview",
				paint: { "line-color": accent, "line-width": 2 },
			});
			map.addLayer({
				id: "preview-point",
				type: "circle",
				source: "preview",
				paint: {
					"circle-radius": 6,
					"circle-color": "#cb4b16",
					"circle-stroke-width": 1.5,
					"circle-stroke-color": "#073642",
				},
				filter: ["==", "$type", "Point"],
			});
		});
		map.on("moveend", () => {
			if (applyingRef.current) return;
			const center = map.getCenter();
			onViewChangeRef.current?.({
				longitude: center.lng,
				latitude: center.lat,
				zoom: map.getZoom(),
			});
		});
		mapRef.current = map;
		return () => {
			map.remove();
			mapRef.current = null;
		};
	}, [accent]);

	useEffect(() => {
		const map = mapRef.current;
		if (!map || !view) return;
		const center = map.getCenter();
		const same =
			Math.abs(center.lng - view.longitude) < 1e-6 &&
			Math.abs(center.lat - view.latitude) < 1e-6 &&
			Math.abs(map.getZoom() - view.zoom) < 1e-4;
		if (same) return;
		applyingRef.current = true;
		map.jumpTo({ center: [view.longitude, view.latitude], zoom: view.zoom });
		map.once("idle", () => {
			applyingRef.current = false;
		});
	}, [view]);

	useEffect(() => {
		const map = mapRef.current;
		if (!map) return;
		const data = asFeatureCollection(geojson) || EMPTY;
		const apply = () => {
			const source = map.getSource("preview") as
				| maplibregl.GeoJSONSource
				| undefined;
			if (!source) return;
			source.setData(data as FeatureCollection);
			if (view) return;
			const features = data.features || [];
			if (!features.length) return;
			const bounds = new maplibregl.LngLatBounds();
			for (const feature of features) {
				extendBounds(bounds, feature.geometry);
			}
			if (!bounds.isEmpty()) {
				applyingRef.current = true;
				map.fitBounds(bounds, { padding: 32, maxZoom: 12, duration: 400 });
				map.once("idle", () => {
					applyingRef.current = false;
					const center = map.getCenter();
					onViewChangeRef.current?.({
						longitude: center.lng,
						latitude: center.lat,
						zoom: map.getZoom(),
					});
				});
			}
		};
		if (map.isStyleLoaded()) apply();
		else map.once("load", apply);
	}, [geojson, view]);

	return <div ref={containerRef} className="map-viewer" />;
}
