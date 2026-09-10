from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlparse, urlunparse

import httpx

from app.core.paths import workspace_subdir
from app.nodes.base import Base4GIxNode, _as_feature_collection


class RestWfsReaderNode(Base4GIxNode):
    node_type = "rest_wfs_reader"
    category = "Reader"
    is_spatial = True
    label = "REST / WFS Reader"
    description = "Interroge un WFS OGC, une API GeoJSON ou Overpass, avec pagination et cache local."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "REST / WFS Reader",
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "title": "Type de source",
                    "enum": ["wfs", "rest_geojson", "overpass"],
                    "enumNames": ["WFS OGC", "API REST GeoJSON", "Overpass OSM"],
                    "default": "wfs",
                },
                "url": {
                    "type": "string",
                    "title": "URL",
                    "default": "https://data.geopf.fr/wfs/ows",
                    "description": "Endpoint WFS, API REST ou Overpass.",
                },
                "type_name": {
                    "type": "string",
                    "title": "TypeName WFS",
                    "description": "Ex. CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle",
                },
                "bbox": {
                    "type": "string",
                    "title": "BBOX (minx,miny,maxx,maxy)",
                    "description": "Optionnel, CRS de la requête.",
                },
                "max_features": {
                    "type": "integer",
                    "title": "Max entités",
                    "default": 200,
                    "minimum": 1,
                    "maximum": 5000,
                },
                "page_size": {
                    "type": "integer",
                    "title": "Taille de page",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "bearer_token": {
                    "type": "string",
                    "title": "Bearer Token",
                    "description": "Ajouté dans Authorization si renseigné.",
                },
                "use_cache": {
                    "type": "boolean",
                    "title": "Utiliser le cache GeoJSON",
                    "default": True,
                },
            },
            "required": ["url"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        source_type = (params.get("source_type") or "wfs").lower()
        url = (params.get("url") or "").strip()
        if not url:
            raise ValueError("URL obligatoire.")
        max_features = int(params.get("max_features") or 200)
        page_size = int(params.get("page_size") or 100)
        type_name = params.get("type_name") or ""
        bbox = (params.get("bbox") or "").strip()
        token = (params.get("bearer_token") or "").strip()
        use_cache = params.get("use_cache", True)

        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "source_type": source_type,
                    "url": url,
                    "type_name": type_name,
                    "bbox": bbox,
                    "max_features": max_features,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
        cache_dir = workspace_subdir("cache")
        cache_path = cache_dir / f"wfs_{cache_key}.geojson"
        if use_cache and cache_path.exists():
            fc = json.loads(cache_path.read_text(encoding="utf-8"))
            return _result(fc, source_type, url, cached=True, cache_path=str(cache_path))

        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        with httpx.Client(timeout=45.0, follow_redirects=True, headers=headers) as client:
            if source_type == "overpass":
                payload = _fetch_overpass(client, url, max_features)
            elif source_type == "rest_geojson":
                payload = _fetch_rest(client, url, max_features)
            else:
                payload = _fetch_wfs(client, url, type_name, bbox, max_features, page_size)

        fc = _as_feature_collection(payload)
        if fc is None:
            raise ValueError("La réponse n'est pas un GeoJSON / WFS FeatureCollection.")
        fc["features"] = (fc.get("features") or [])[:max_features]
        cache_path.write_text(json.dumps(fc), encoding="utf-8")
        return _result(fc, source_type, url, cached=False, cache_path=str(cache_path))


def _result(fc: Dict[str, Any], source_type: str, url: str, cached: bool, cache_path: str) -> Dict[str, Any]:
    return {
        "data": fc,
        "metadata": {
            "kind": "vector",
            "source": source_type,
            "url": url,
            "feature_count": len(fc.get("features") or []),
            "cached": cached,
            "cache_path": cache_path,
            "crs": "EPSG:4326",
        },
    }


def _fetch_wfs(
    client: httpx.Client,
    url: str,
    type_name: str,
    bbox: str,
    max_features: int,
    page_size: int,
) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []
    start = 0
    while len(features) < max_features:
        count = min(page_size, max_features - len(features))
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "OUTPUTFORMAT": "application/json",
            "COUNT": str(count),
            "STARTINDEX": str(start),
        }
        if type_name:
            params["TYPENAMES"] = type_name
            params["TYPENAME"] = type_name
        if bbox:
            params["BBOX"] = bbox
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        page = payload.get("features") or []
        features.extend(page)
        if len(page) < count:
            break
        start += count
    return {"type": "FeatureCollection", "features": features}


def _fetch_rest(client: httpx.Client, url: str, max_features: int) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []
    next_url: Optional[str] = url
    while next_url and len(features) < max_features:
        response = client.get(next_url)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            features.extend(payload)
            break
        page = payload.get("features") or payload.get("results") or []
        if page and isinstance(page, list) and isinstance(page[0], dict) and "geometry" not in page[0] and "properties" not in page[0]:
            features.extend(
                {
                    "type": "Feature",
                    "properties": item,
                    "geometry": item.get("geometry") or item.get("_geoloc"),
                }
                for item in page
            )
        else:
            features.extend(page)
        next_url = None
        links = payload.get("links") or payload.get("next")
        if isinstance(links, str):
            next_url = links
        elif isinstance(links, list):
            for link in links:
                if isinstance(link, dict) and str(link.get("rel") or "").lower() in {"next", "next-page"}:
                    next_url = link.get("href")
                    break
        if not next_url:
            break
    return {"type": "FeatureCollection", "features": features[:max_features]}


def _fetch_overpass(client: httpx.Client, url: str, max_features: int) -> Dict[str, Any]:
    query = url
    endpoint = "https://overpass-api.de/api/interpreter"
    parsed = urlparse(url)
    if "overpass" in (parsed.netloc or "") and parsed.query:
        query = dict(parse_qsl(parsed.query)).get("data") or url
        endpoint = urlunparse(parsed._replace(query=""))
    elif parsed.scheme in {"http", "https"} and "overpass" in (parsed.netloc or "") and not parsed.query:
        endpoint = url
        query = "[out:json][timeout:25];(node(48.85,2.34,48.87,2.36););out 50;"
    response = client.post(endpoint, data={"data": query})
    response.raise_for_status()
    payload = response.json()
    features = []
    for element in payload.get("elements") or []:
        if element.get("type") == "node" and "lon" in element and "lat" in element:
            features.append(
                {
                    "type": "Feature",
                    "properties": {"id": element.get("id"), **(element.get("tags") or {})},
                    "geometry": {"type": "Point", "coordinates": [element["lon"], element["lat"]]},
                }
            )
        if len(features) >= max_features:
            break
    return {"type": "FeatureCollection", "features": features}
