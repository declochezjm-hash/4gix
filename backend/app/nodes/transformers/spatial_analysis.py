from __future__ import annotations

from typing import Any, Dict, List

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString
from shapely.ops import polygonize, unary_union

from app.nodes.base import Base4GIxNode
from app.nodes.fme_features import (
    feature_from_shapely,
    input_features,
    ports_payload,
    shapely_of,
)


def _gdf(features: List[Dict[str, Any]], crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    if not features:
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    return gpd.GeoDataFrame.from_features(features, crs=crs)


def _gdf_features(gdf: gpd.GeoDataFrame, feature_type: str) -> List[Dict[str, Any]]:
    if gdf.empty:
        return []
    out: List[Dict[str, Any]] = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        props = {k: v for k, v in row.items() if k != "geometry"}
        out.append(feature_from_shapely(geom, props, feature_type=feature_type))
    return out


def _project(gdf: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    if str(gdf.crs) != crs:
        return gdf.to_crs(crs)
    return gdf


class BuffererNode(Base4GIxNode):
    node_type = "bufferer"
    category = "Transformer"
    is_spatial = True
    label = "Bufferer"
    description = "Zones tampons plates ou arrondies. Distance en mètres (reprojection auto si WGS84)."
    fme_group = "Spatial Analysis"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Bufferer",
            "type": "object",
            "properties": {
                "distance": {
                    "type": "number",
                    "title": "Distance (m)",
                    "format": "slider",
                    "default": 200,
                    "minimum": 1,
                    "maximum": 5000,
                },
                "cap_style": {
                    "type": "string",
                    "title": "Extrémités",
                    "enum": ["round", "flat", "square"],
                    "enumNames": ["Arrondi", "Plat", "Carré"],
                    "default": "round",
                },
                "resolution": {"type": "integer", "title": "Résolution", "default": 16},
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        distance = float(params.get("distance") or 200)
        cap = {"round": 1, "flat": 2, "square": 3}.get(str(params.get("cap_style") or "round"), 1)
        resolution = int(params.get("resolution") or 16)
        out = []
        for feature in input_features(inputs):
            geom = shapely_of(feature)
            if geom is None:
                out.append(feature)
                continue
            gdf = _gdf([feature])
            metric = _project(gdf, "EPSG:2154")
            buffered = metric.geometry.iloc[0].buffer(distance, resolution=resolution, cap_style=cap)
            metric.geometry = [buffered]
            restored = _project(metric, "EPSG:4326").geometry.iloc[0]
            out.append(feature_from_shapely(restored, feature.get("properties"), feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type, extra_meta={"distance_m": distance})


class ClipperNode(Base4GIxNode):
    node_type = "clipper"
    category = "Transformer"
    is_spatial = True
    label = "Clipper"
    description = "Découpe Inside / Outside par un masque polygonal."
    input_handles = ["input", "clipper"]
    output_handles = ["inside", "outside"]
    fme_group = "Spatial Analysis"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Clipper",
            "type": "object",
            "properties": {
                "keep_empty": {"type": "boolean", "title": "Conserver les géométries vides", "default": False},
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        keep_empty = bool(params.get("keep_empty", False))
        clip_geoms = [shapely_of(f) for f in input_features(inputs, "clipper")]
        clip_geoms = [g for g in clip_geoms if g is not None and not g.is_empty]
        if not clip_geoms:
            raise ValueError("Clipper : reliez un masque polygonal sur la poignée `clipper`.")
        mask = unary_union(clip_geoms)
        inside, outside = [], []
        for feature in input_features(inputs, "input"):
            geom = shapely_of(feature)
            props = feature.get("properties")
            if geom is None:
                outside.append(feature)
                continue
            inter = geom.intersection(mask)
            diff = geom.difference(mask)
            if not inter.is_empty:
                inside.append(feature_from_shapely(inter, props, feature_type=self.node_type))
            elif keep_empty:
                inside.append(feature_from_shapely(inter, props, feature_type=self.node_type))
            if not diff.is_empty:
                outside.append(feature_from_shapely(diff, props, feature_type=self.node_type))
            elif keep_empty:
                outside.append(feature_from_shapely(diff, props, feature_type=self.node_type))
        return ports_payload(
            {"inside": inside, "outside": outside},
            feature_type=self.node_type,
            primary="inside",
        )


class DissolverNode(Base4GIxNode):
    node_type = "dissolver"
    category = "Transformer"
    is_spatial = True
    label = "Dissolver"
    description = "Fusionne les polygones contigus partageant des attributs communs."
    fme_group = "Spatial Analysis"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Dissolver",
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "string",
                    "title": "Attribut de groupement",
                    "default": "group",
                    "description": "Vide = union totale.",
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        feats = input_features(inputs)
        gdf = _gdf(feats)
        if gdf.empty:
            return ports_payload({"output": []}, feature_type=self.node_type)
        group_by = (params.get("group_by") or "").strip()
        drop_cols = [c for c in gdf.columns if c.startswith("fme_") and c != group_by]
        work = gdf.drop(columns=drop_cols, errors="ignore")
        if group_by and group_by in work.columns:
            dissolved = work.dissolve(by=group_by, as_index=False)
        else:
            dissolved = work.dissolve(as_index=False)
        return ports_payload(
            {"output": _gdf_features(dissolved, self.node_type)},
            feature_type=self.node_type,
            extra_meta={"group_by": group_by or None, "in": len(feats), "out": len(dissolved)},
        )


class AreaOnAreaOverlayerNode(Base4GIxNode):
    node_type = "area_on_area_overlayer"
    category = "Transformer"
    is_spatial = True
    label = "AreaOnAreaOverlayer"
    description = "Intersection croisée N×N de polygones avec conservation des identifiants d'origine."
    fme_group = "Spatial Analysis"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "AreaOnAreaOverlayer",
            "type": "object",
            "properties": {
                "id_attr": {"type": "string", "title": "Attribut identifiant", "default": "name"},
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        id_attr = params.get("id_attr") or "name"
        sources = []
        boundaries = []
        for idx, feature in enumerate(input_features(inputs)):
            geom = shapely_of(feature)
            if geom is None or geom.is_empty:
                continue
            if geom.geom_type == "MultiPolygon":
                parts = list(geom.geoms)
            elif geom.geom_type == "Polygon":
                parts = [geom]
            else:
                continue
            fid = (feature.get("properties") or {}).get(id_attr, idx)
            for part in parts:
                sources.append((fid, feature, part))
                boundaries.append(part.boundary)
        if not boundaries:
            return ports_payload({"output": []}, feature_type=self.node_type)
        pieces = list(polygonize(unary_union(boundaries)))
        out = []
        for piece in pieces:
            if piece.is_empty or piece.area <= 0:
                continue
            seed = piece.representative_point()
            ids = []
            props: Dict[str, Any] = {}
            for fid, feature, part in sources:
                if part.covers(seed) or part.intersects(piece):
                    if part.intersection(piece).area > 1e-12:
                        ids.append(fid)
                        for key, value in (feature.get("properties") or {}).items():
                            props.setdefault(key, value)
            props["_overlay_ids"] = ids
            props["_overlay_count"] = len(ids)
            if ids:
                out.append(feature_from_shapely(piece, props, feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)


class LineOnLineOverlayerNode(Base4GIxNode):
    node_type = "line_on_line_overlayer"
    category = "Transformer"
    is_spatial = True
    label = "LineOnLineOverlayer"
    description = "Découpe un réseau de lignes à chaque intersection."
    fme_group = "Spatial Analysis"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {"title": "LineOnLineOverlayer", "type": "object", "properties": {}}

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        lines = []
        for feature in input_features(inputs):
            geom = shapely_of(feature)
            if geom is None:
                continue
            if geom.geom_type in {"LineString", "MultiLineString"}:
                lines.append(geom)
        if not lines:
            return ports_payload({"output": []}, feature_type=self.node_type)
        noded = unary_union(lines)
        parts: List[Any] = []
        if isinstance(noded, LineString):
            parts = [noded]
        elif isinstance(noded, MultiLineString):
            parts = list(noded.geoms)
        else:
            parts = [noded]
        out = [
            feature_from_shapely(part, {"segment_id": i}, feature_type=self.node_type)
            for i, part in enumerate(parts)
            if part and not part.is_empty
        ]
        return ports_payload({"output": out}, feature_type=self.node_type, extra_meta={"segments": len(out)})


class CentroidExtractorNode(Base4GIxNode):
    node_type = "centroid_extractor"
    category = "Transformer"
    is_spatial = True
    label = "CentroidExtractor"
    description = "Remplace chaque géométrie par son centroïde (CenterPointReplacer)."
    fme_group = "Spatial Analysis"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "CentroidExtractor",
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "title": "Mode",
                    "enum": ["centroid", "representative"],
                    "enumNames": ["Centroïde", "Point intérieur"],
                    "default": "centroid",
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        mode = params.get("mode") or "centroid"
        out = []
        for feature in input_features(inputs):
            geom = shapely_of(feature)
            if geom is None:
                out.append(feature)
                continue
            point = geom.representative_point() if mode == "representative" else geom.centroid
            out.append(feature_from_shapely(point, feature.get("properties"), feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)


class BoundingBoxReplacerNode(Base4GIxNode):
    node_type = "bounding_box_replacer"
    category = "Transformer"
    is_spatial = True
    label = "BoundingBoxReplacer"
    description = "Remplace la géométrie par son emprise rectangulaire (Envelope)."
    fme_group = "Spatial Analysis"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {"title": "BoundingBoxReplacer", "type": "object", "properties": {}}

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        out = []
        for feature in input_features(inputs):
            geom = shapely_of(feature)
            if geom is None:
                out.append(feature)
                continue
            out.append(feature_from_shapely(geom.envelope, feature.get("properties"), feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)


class DensifierNode(Base4GIxNode):
    node_type = "densifier"
    category = "Transformer"
    is_spatial = True
    label = "Densifier"
    description = "Ajoute des sommets intermédiaires selon une distance maximale (mètres)."
    fme_group = "Spatial Analysis"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Densifier",
            "type": "object",
            "properties": {
                "max_distance": {
                    "type": "number",
                    "title": "Distance max (m)",
                    "format": "slider",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 2000,
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        max_distance = float(params.get("max_distance") or 50)
        out = []
        for feature in input_features(inputs):
            geom = shapely_of(feature)
            if geom is None or not hasattr(geom, "segmentize"):
                out.append(feature)
                continue
            gdf = _project(_gdf([feature]), "EPSG:2154")
            densified = gdf.geometry.iloc[0].segmentize(max_distance)
            gdf.geometry = [densified]
            restored = _project(gdf, "EPSG:4326").geometry.iloc[0]
            out.append(feature_from_shapely(restored, feature.get("properties"), feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)


class GeneralizerNode(Base4GIxNode):
    node_type = "generalizer"
    category = "Transformer"
    is_spatial = True
    label = "Generalizer"
    description = "Simplification Douglas-Peucker / réduction de sommets."
    fme_group = "Spatial Analysis"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Generalizer",
            "type": "object",
            "properties": {
                "tolerance": {
                    "type": "number",
                    "title": "Tolérance (m)",
                    "format": "slider",
                    "default": 10,
                    "minimum": 0.1,
                    "maximum": 500,
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        tolerance = float(params.get("tolerance") or 10)
        out = []
        for feature in input_features(inputs):
            geom = shapely_of(feature)
            if geom is None:
                out.append(feature)
                continue
            gdf = _project(_gdf([feature]), "EPSG:2154")
            simplified = gdf.geometry.iloc[0].simplify(tolerance, preserve_topology=True)
            gdf.geometry = [simplified]
            restored = _project(gdf, "EPSG:4326").geometry.iloc[0]
            out.append(feature_from_shapely(restored, feature.get("properties"), feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)
