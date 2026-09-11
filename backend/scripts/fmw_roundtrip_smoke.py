"""Smoke test import → export → re-import (.fmw). Run inside the API container."""

from __future__ import annotations

import sys
from pathlib import Path

from app.core.fmw_project_parser import export_fmw, parse_fmw


def main() -> int:
    sample_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not sample_path or not sample_path.is_file():
        print("Usage: python scripts/fmw_roundtrip_smoke.py /path/to/sample.fmw", file=sys.stderr)
        return 2

    text = sample_path.read_text(encoding="utf-8")
    first = parse_fmw(text, default_name=sample_path.stem)
    n0 = len(first["definition"]["nodes"])
    e0 = len(first["definition"]["edges"])

    exported = export_fmw(first["definition"], name=first["name"])
    second = parse_fmw(exported, default_name="roundtrip")
    n1 = len(second["definition"]["nodes"])
    e1 = len(second["definition"]["edges"])

    types0 = sorted(
        (node.get("data") or {}).get("nodeType") or "" for node in first["definition"]["nodes"]
    )
    types1 = sorted(
        (node.get("data") or {}).get("nodeType") or "" for node in second["definition"]["nodes"]
    )

    ok = n0 == n1 and e0 == e1 and types0 == types1
    print(f"nodes: {n0} -> {n1}, edges: {e0} -> {e1}, types_match: {types0 == types1}")
    if second["warnings"]:
        print("warnings:", "; ".join(second["warnings"][:5]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
