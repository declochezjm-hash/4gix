import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type GeoJsonFeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: string;
    geometry?: { type: string; coordinates: unknown } | null;
    properties?: Record<string, unknown>;
  }>;
};

type MapViewerProps = {
  geojson?: GeoJsonFeatureCollection | Record<string, unknown> | null;
};

const EMPTY: GeoJsonFeatureCollection = { type: "FeatureCollection", features: [] };

export function MapViewer({ geojson }: MapViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

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
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("preview", { type: "geojson", data: EMPTY });
      map.addLayer({
        id: "preview-fill",
        type: "fill",
        source: "preview",
        paint: { "fill-color": "#2aa198", "fill-opacity": 0.28 },
        filter: ["==", "$type", "Polygon"],
      });
      map.addLayer({
        id: "preview-line",
        type: "line",
        source: "preview",
        paint: { "line-color": "#2aa198", "line-width": 2 },
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
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const data = (geojson as GeoJsonFeatureCollection) || EMPTY;
    const apply = () => {
      const source = map.getSource("preview") as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(data);
        const features = data.features || [];
        if (features.length) {
          const bounds = new maplibregl.LngLatBounds();
          for (const feature of features) {
            const geom = feature.geometry;
            if (!geom) continue;
            if (geom.type === "Point") {
              bounds.extend(geom.coordinates as [number, number]);
            } else if (geom.type === "LineString") {
              for (const coord of geom.coordinates) bounds.extend(coord as [number, number]);
            } else if (geom.type === "Polygon") {
              for (const ring of geom.coordinates) {
                for (const coord of ring) bounds.extend(coord as [number, number]);
              }
            } else if (geom.type === "MultiPoint") {
              for (const coord of geom.coordinates) bounds.extend(coord as [number, number]);
            }
          }
          if (!bounds.isEmpty()) {
            map.fitBounds(bounds, { padding: 32, maxZoom: 12, duration: 400 });
          }
        }
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [geojson]);

  return <div ref={containerRef} className="map-viewer" />;
}
