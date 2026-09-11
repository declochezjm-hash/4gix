from __future__ import annotations

import ast
import json
from typing import Any, Dict, List

from app.nodes.base import Base4GIxNode
from app.nodes.fme_features import feature_from_shapely, input_features, ports_payload, shapely_of

SAFE_FUNCS = {
    "abs": abs,
    "str": str,
    "int": int,
    "float": float,
    "len": len,
    "round": round,
    "min": min,
    "max": max,
    "True": True,
    "False": False,
    "None": None,
}


def _eval_expr(expr: str, props: Dict[str, Any]) -> Any:
    if expr is None or str(expr).strip() == "":
        return None
    source = str(expr)
    try:
        ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Expression invalide: {expr}") from exc
    return eval(source, {"__builtins__": {}}, {**SAFE_FUNCS, **props})  # noqa: S307


def _compare(left: Any, op: str, right: Any) -> bool:
    op = (op or "eq").lower()
    if op in {"isnull", "isempty"}:
        return left is None or str(left).strip() == ""
    if op == "notnull":
        return left is not None and str(left).strip() != ""
    if op == "contains":
        return str(right).lower() in str(left).lower()
    if op in {"eq", "neq", "gt", "gte", "lt", "lte"}:
        try:
            left_n = float(left)
            right_n = float(right)
            numeric = True
        except (TypeError, ValueError):
            left_n, right_n, numeric = str(left), str(right), False
        if op == "eq":
            return left_n == right_n if numeric else str(left) == str(right)
        if op == "neq":
            return left_n != right_n if numeric else str(left) != str(right)
        if not numeric:
            return False
        if op == "gt":
            return left_n > right_n
        if op == "gte":
            return left_n >= right_n
        if op == "lt":
            return left_n < right_n
        if op == "lte":
            return left_n <= right_n
    return False


def _parse_json(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    return json.loads(raw)


class AttributeManagerNode(Base4GIxNode):
    node_type = "attribute_manager"
    category = "Transformer"
    is_spatial = False
    label = "Edit Fields"
    description = "Add, rename, remove or modify attributes"
    fme_group = "Attribute Operations"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "AttributeManager",
            "type": "object",
            "properties": {
                "operations": {
                    "type": "string",
                    "title": "Opérations JSON",
                    "format": "textarea",
                    "default": '[{"op":"rename","from":"name","to":"nom"},{"op":"create","name":"source","expr":"\'4gix\'"}]',
                    "description": "Liste {op: rename|create|delete|type, ...}.",
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        operations = _parse_json(params.get("operations"), [])
        out = []
        for feature in input_features(inputs):
            props = dict(feature.get("properties") or {})
            for action in operations:
                op = (action.get("op") or "").lower()
                if op == "rename" and action.get("from") in props:
                    props[action.get("to")] = props.pop(action.get("from"))
                elif op == "delete":
                    props.pop(action.get("name"), None)
                elif op == "create":
                    props[action.get("name")] = _eval_expr(action.get("expr") or action.get("value") or "None", props)
                elif op == "type":
                    name = action.get("name")
                    dtype = (action.get("dtype") or "str").lower()
                    if name in props and props[name] is not None:
                        caster = {"int": int, "float": float, "str": str, "bool": bool}.get(dtype, str)
                        try:
                            props[name] = caster(props[name])
                        except (TypeError, ValueError):
                            pass
            out.append(feature_from_shapely(shapely_of(feature), props, feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)


class TesterNode(Base4GIxNode):
    node_type = "tester"
    category = "Transformer"
    is_spatial = False
    label = "If / Filter Condition"
    description = "Validate conditions on feature fields"
    output_handles = ["passed", "failed"]
    fme_group = "Attribute Operations"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Tester",
            "type": "object",
            "properties": {
                "logic": {
                    "type": "string",
                    "title": "Logique",
                    "enum": ["AND", "OR"],
                    "default": "AND",
                },
                "clauses": {
                    "type": "string",
                    "title": "Clauses JSON",
                    "format": "textarea",
                    "default": '[{"attr":"category","op":"eq","value":"urban"}]',
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        logic = (params.get("logic") or "AND").upper()
        clauses = _parse_json(params.get("clauses"), [])
        passed, failed = [], []
        for feature in input_features(inputs):
            props = feature.get("properties") or {}
            results = [_compare(props.get(c.get("attr")), c.get("op") or "eq", c.get("value")) for c in clauses]
            ok = all(results) if logic == "AND" else any(results)
            if not clauses:
                ok = True
            (passed if ok else failed).append(feature)
        return ports_payload({"passed": passed, "failed": failed}, feature_type=self.node_type, primary="passed")


class TestFilterNode(Base4GIxNode):
    node_type = "test_filter"
    category = "Transformer"
    is_spatial = False
    label = "Switch / Multi-Condition"
    description = "Route features based on rules"
    output_handles = ["output1", "output2", "output3", "else"]
    fme_group = "Attribute Operations"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "TestFilter",
            "type": "object",
            "properties": {
                "conditions": {
                    "type": "string",
                    "title": "Conditions JSON",
                    "format": "textarea",
                    "default": '[{"port":"output1","attr":"category","op":"eq","value":"urban"},{"port":"output2","attr":"category","op":"eq","value":"rural"}]',
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        conditions = _parse_json(params.get("conditions"), [])
        buckets: Dict[str, List[Dict[str, Any]]] = {name: [] for name in self.output_handles}
        for feature in input_features(inputs):
            props = feature.get("properties") or {}
            routed = False
            for index, condition in enumerate(conditions):
                port = str(condition.get("port") or f"output{index + 1}").lower()
                if _compare(props.get(condition.get("attr")), condition.get("op") or "eq", condition.get("value")):
                    buckets.setdefault(port, []).append(feature)
                    routed = True
                    break
            if not routed:
                buckets["else"].append(feature)
        return ports_payload(buckets, feature_type=self.node_type, primary="output1")


class ListExploderNode(Base4GIxNode):
    node_type = "list_exploder"
    category = "Transformer"
    is_spatial = False
    label = "Split List Array"
    description = "Flatten list attributes into features"
    fme_group = "Attribute Operations"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "ListExploder",
            "type": "object",
            "properties": {
                "list_attr": {"type": "string", "title": "Attribut liste", "default": "items"},
                "item_attr": {"type": "string", "title": "Nom de l'élément explosé", "default": "item"},
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        list_attr = params.get("list_attr") or "items"
        item_attr = params.get("item_attr") or "item"
        out = []
        for feature in input_features(inputs):
            props = dict(feature.get("properties") or {})
            raw = props.get(list_attr)
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    raw = [raw]
            if not isinstance(raw, list) or not raw:
                out.append(feature)
                continue
            for index, item in enumerate(raw):
                exploded = dict(props)
                exploded[item_attr] = item
                exploded["_list_index"] = index
                if isinstance(item, dict):
                    exploded.update(item)
                out.append(feature_from_shapely(shapely_of(feature), exploded, feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)


class CounterNode(Base4GIxNode):
    node_type = "counter"
    category = "Transformer"
    is_spatial = False
    label = "Increment Counter"
    description = "Add sequence number or ID"
    fme_group = "Attribute Operations"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Counter",
            "type": "object",
            "properties": {
                "attr": {"type": "string", "title": "Nom de l'attribut", "default": "_count"},
                "start": {"type": "integer", "title": "Valeur de départ", "default": 1},
                "increment": {"type": "integer", "title": "Incrément", "default": 1},
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        attr = params.get("attr") or "_count"
        start = int(params.get("start") or 1)
        increment = int(params.get("increment") or 1)
        out = []
        value = start
        for feature in input_features(inputs):
            props = dict(feature.get("properties") or {})
            props[attr] = value
            value += increment
            out.append(feature_from_shapely(shapely_of(feature), props, feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)


class DuplicateFilterNode(Base4GIxNode):
    node_type = "duplicate_filter"
    category = "Transformer"
    is_spatial = False
    label = "Remove Duplicates"
    description = "Filter out identical records"
    output_handles = ["unique", "duplicate"]
    fme_group = "Attribute Operations"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "DuplicateFilter",
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "title": "Clés (virgules)",
                    "default": "name",
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        keys = [part.strip() for part in str(params.get("keys") or "name").split(",") if part.strip()]
        seen = set()
        unique, duplicate = [], []
        for feature in input_features(inputs):
            props = feature.get("properties") or {}
            token = tuple(str(props.get(key)) for key in keys)
            if token in seen:
                duplicate.append(feature)
            else:
                seen.add(token)
                unique.append(feature)
        return ports_payload({"unique": unique, "duplicate": duplicate}, feature_type=self.node_type, primary="unique")
