"""Lineage graph: index, scope, path, held ancestor. OWNER: M2.

Scope rule (PLAN_T08 §2.3): an artefact is in scope of a request iff request.subject_id is in
artefact.subject_ids. BFS is used for evidence (lineage_path), held ancestors and cross-checks,
NOT to widen the scope (trap B6: descendants of a shared frame may belong to someone else).

STUB (M1 scaffold): minimal versions so the pipeline runs end to end.
TODO M2: build_index (children/parents maps, dangling + cycle warnings), real lineage_path,
held_ancestor via BFS over parents, and tests for trap B6.
"""
from __future__ import annotations

from .contracts import Graph


def build_index(graph: Graph) -> dict:
    """Return {"children": {id: [child ids]}, "warnings": [...]}. STUB: no warnings."""
    children: dict[str, list[str]] = {}
    for a in graph.values():
        for p in a.get("parent_ids", []):
            children.setdefault(p, []).append(a["artefact_id"])
    return {"children": children, "warnings": []}


def scope_for(graph: Graph, subject_id: str) -> list[str]:
    """Artefact ids tagged with subject_id, sorted for deterministic output."""
    return sorted(aid for aid, a in graph.items() if subject_id in a.get("subject_ids", []))


def lineage_path(graph: Graph, artefact_id: str) -> str:
    """Root-to-artefact path, e.g. "a0043 > a0045 > a0046". STUB: only the artefact itself."""
    return artefact_id


def held_ancestor(graph: Graph, artefact_id: str) -> str | None:
    """legal_hold code of the nearest ancestor under hold, or None. STUB: always None."""
    return None
