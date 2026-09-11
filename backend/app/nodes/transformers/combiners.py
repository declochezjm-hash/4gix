from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

import geopandas as gpd

from app.nodes.base import Base4GIxNode
from app.nodes.fme_features import (
    feature_from_shapely,
    input_features,
    ports_payload,
    shapely_of,
)

DE9IM = {
    "intersects": lambda a, b: a.intersects(b),
    "contains": lambda a, b: a.contains(b),
    "touches": lambda a, b: a.touches(b),
    "within": lambda a, b: a.within(b),
    "disjoint": lambda a, b: a.disjoint(b),
    "crosses": lambda a, b: a.crosses(b),
    "overlaps": lambda a, b: a.overlaps(b),
}


class FeatureMergerNode(Base4GIxNode):
    node_type = "feature_merger"
    category = "Transformer"
    is_spatial = False
    label = "FeatureMerger"
    description = "Jointure attributaire 1:N (Merged / Unmerged_Request / Unmerged_Supplier)."
    input_handles = ["request", "supplier"]
    output_handles = ["merged", "unmerged_request", "unmerged_supplier"]
    fme_group = "Combiners & Joins"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "FeatureMerger",
            "type": "object",
            "properties": {
                "request_key": {"type": "string", "title": "Clé Request", "default": "id"},
                "supplier_key": {"type": "string", "title": "Clé Supplier", "default": "id"},
                "prefix_supplier": {"type": "string", "title": "Préfixe attributs Supplier", "default": "sup_"},
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        request_key = params.get("request_key") or "id"
        supplier_key = params.get("supplier_key") or "id"
        prefix = params.get("prefix_supplier") or "sup_"
        requests = input_features(inputs, "request")
        suppliers = input_features(inputs, "supplier")
        index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        used_supplier = set()
        for feature in suppliers:
            key = str((feature.get("properties") or {}).get(supplier_key, ""))
            index[key].append(feature)
        merged, unmerged_request = [], []
        for feature in requests:
            key = str((feature.get("properties") or {}).get(request_key, ""))
            matches = index.get(key) or []
            if not matches:
                unmerged_request.append(feature)
                continue
            req_props = dict(feature.get("properties") or {})
            for supplier in matches:
                used_supplier.add(id(supplier))
                props = dict(req_props)
                for name, value in (supplier.get("properties") or {}).items():
                    props[f"{prefix}{name}"] = value
                geom = shapely_of(feature) or shapely_of(supplier)
                merged.append(feature_from_shapely(geom, props, feature_type=self.node_type))
        unmerged_supplier = [f for f in suppliers if id(f) not in used_supplier]
        return ports_payload(
            {
                "merged": merged,
                "unmerged_request": unmerged_request,
                "unmerged_supplier": unmerged_supplier,
            },
            feature_type=self.node_type,
            primary="merged",
        )


class SpatialRelatorNode(Base4GIxNode):
    node_type = "spatial_relator"
    category = "Transformer"
    is_spatial = True
    label = "Spatial Join / Intersect"
    description = "Match features by location"
    input_handles = ["request", "supplier"]
    output_handles = ["related", "unrelated"]
    fme_group = "Combiners & Joins"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "SpatialRelator",
            "type": "object",
            "properties": {
                "predicate": {
                    "type": "string",
                    "title": "Relation DE-9IM",
                    "enum": list(DE9IM.keys()),
                    "enumNames": ["INTERSECTS", "CONTAINS", "TOUCHES", "WITHIN", "DISJOINT", "CROSSES", "OVERLAPS"],
                    "default": "intersects",
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        predicate = (params.get("predicate") or "intersects").lower()
        tester = DE9IM.get(predicate)
        if tester is None:
            raise ValueError(f"Relation spatiale inconnue: {predicate}")
        suppliers = [(shapely_of(f), f) for f in input_features(inputs, "supplier")]
        suppliers = [(g, f) for g, f in suppliers if g is not None]
        related, unrelated = [], []
        for feature in input_features(inputs, "request"):
            geom = shapely_of(feature)
            hits = []
            if geom is not None:
                for other, src in suppliers:
                    if tester(geom, other):
                        hits.append((src.get("properties") or {}).get("name") or (src.get("properties") or {}).get("id"))
            props = dict(feature.get("properties") or {})
            props["_related_count"] = len(hits)
            props["_related_ids"] = hits
            tagged = feature_from_shapely(geom, props, feature_type=self.node_type)
            (related if hits else unrelated).append(tagged)
        return ports_payload(
            {"related": related, "unrelated": unrelated},
            feature_type=self.node_type,
            primary="related",
            extra_meta={"predicate": predicate},
        )


class NeighborFinderNode(Base4GIxNode):
    node_type = "neighbor_finder"
    category = "Transformer"
    is_spatial = True
    label = "NeighborFinder"
    description = "Associe les K plus proches voisins entre deux couches spatiales."
    input_handles = ["base", "candidates"]
    fme_group = "Combiners & Joins"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "NeighborFinder",
            "type": "object",
            "properties": {
                "k": {"type": "integer", "title": "Nombre de voisins (K)", "default": 1, "minimum": 1, "maximum": 10},
                "max_distance": {
                    "type": "number",
                    "title": "Distance max (m)",
                    "default": 50000,
                    "minimum": 1,
                    "maximum": 500000,
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        k = max(1, int(params.get("k") or 1))
        max_distance = float(params.get("max_distance") or 50000)
        base_feats = input_features(inputs, "base")
        cand_feats = input_features(inputs, "candidates")
        if not base_feats:
            raise ValueError("NeighborFinder : flux `base` vide.")
        if not cand_feats:
            raise ValueError("NeighborFinder : flux `candidates` vide.")
        base = gpd.GeoDataFrame.from_features(base_feats, crs="EPSG:4326").to_crs("EPSG:2154")
        cand = gpd.GeoDataFrame.from_features(cand_feats, crs="EPSG:4326").to_crs("EPSG:2154")
        cand = cand.reset_index(drop=True)
        cand["_cand_idx"] = cand.index
        joined = gpd.sjoin_nearest(
            base,
            cand,
            how="left",
            max_distance=max_distance,
            distance_col="_neighbor_dist",
        )
        if k > 1:
            # sjoin_nearest returns 1 neighbour; approximate extra k via distance rank
            extra_rows = []
            cand_geoms = list(cand.geometry)
            for i, row in base.iterrows():
                geom = row.geometry
                dists = sorted(
                    ((geom.distance(other), j) for j, other in enumerate(cand_geoms) if other is not None),
                )[:k]
                props = {c: row[c] for c in base.columns if c != "geometry"}
                for rank, (dist, j) in enumerate(dists, start=1):
                    extra = dict(props)
                    extra["_neighbor_rank"] = rank
                    extra["_neighbor_dist"] = dist
                    for col, value in cand.iloc[j].items():
                        if col != "geometry":
                            extra[f"nb_{col}"] = value
                    extra_rows.append(feature_from_shapely(geom, extra, feature_type=self.node_type, crs="EPSG:2154"))
            restored = []
            for feature in extra_rows:
                gdf = gpd.GeoDataFrame.from_features([feature], crs="EPSG:2154").to_crs("EPSG:4326")
                restored.extend(
                    [
                        feature_from_shapely(
                            gdf.geometry.iloc[0],
                            {k: v for k, v in gdf.iloc[0].items() if k != "geometry"},
                            feature_type=self.node_type,
                        )
                    ]
                )
            return ports_payload({"output": restored}, feature_type=self.node_type)

        out = []
        restored = joined.to_crs("EPSG:4326")
        for _, row in restored.iterrows():
            props = {c: v for c, v in row.items() if c != "geometry"}
            out.append(feature_from_shapely(row.geometry, props, feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)
