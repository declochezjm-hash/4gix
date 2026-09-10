export type GeoJsonFeature = {
	type: string;
	geometry?: { type: string; coordinates: unknown } | null;
	properties?: Record<string, unknown>;
};

export type GeoJsonFeatureCollection = {
	type: "FeatureCollection";
	features: GeoJsonFeature[];
	crs?: unknown;
	truncated?: boolean;
	total?: number;
};

export function isFeatureCollection(
	value: unknown,
): value is GeoJsonFeatureCollection {
	return Boolean(
		value &&
			typeof value === "object" &&
			(value as { type?: string }).type === "FeatureCollection" &&
			Array.isArray((value as { features?: unknown }).features),
	);
}

export function asFeatureCollection(
	value: unknown,
): GeoJsonFeatureCollection | null {
	if (!value) return null;
	if (isFeatureCollection(value)) return value;
	if (typeof value === "object") {
		const record = value as Record<string, unknown>;
		if (record.type === "Feature" && record.geometry) {
			return { type: "FeatureCollection", features: [value as GeoJsonFeature] };
		}
		if (record.data) return asFeatureCollection(record.data);
		if (record.geojson) return asFeatureCollection(record.geojson);
		if (record.preview) return asFeatureCollection(record.preview);
		const nested: GeoJsonFeature[] = [];
		for (const item of Object.values(record)) {
			const fc = asFeatureCollection(item);
			if (fc) nested.push(...fc.features);
		}
		if (nested.length) {
			return { type: "FeatureCollection", features: nested };
		}
	}
	return null;
}

export function tableRowsFromData(value: unknown): {
	columns: string[];
	rows: Record<string, unknown>[];
} {
	const fc = asFeatureCollection(value);
	if (fc) {
		const columns: string[] = [];
		const rows = fc.features.map((feature) => {
			const props = { ...(feature.properties || {}) };
			if (feature.geometry?.type) props._geom = feature.geometry.type;
			for (const key of Object.keys(props)) {
				if (!columns.includes(key)) columns.push(key);
			}
			return props;
		});
		return { columns, rows };
	}
	if (value && typeof value === "object") {
		const record = value as Record<string, unknown>;
		if (Array.isArray(record.records)) {
			const rows = record.records as Record<string, unknown>[];
			const columns: string[] = [];
			for (const row of rows) {
				for (const key of Object.keys(row || {})) {
					if (!columns.includes(key)) columns.push(key);
				}
			}
			return { columns, rows };
		}
	}
	return { columns: [], rows: [] };
}
