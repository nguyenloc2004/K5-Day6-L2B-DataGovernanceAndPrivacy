"""Lineage graph: index, scope, path, held ancestor. OWNER: M2.

Scope rule (PLAN_T08 §2.3):
  An artefact is in scope of a request iff request.subject_id is in artefact.subject_ids.
  BFS is used for evidence (lineage_path), discovering held ancestors, and cross-checks,
  NOT to widen the scope (trap B6: descendants of a shared frame may belong to someone else).

Responsibilities:
  - build_index: children/parents/ancestors maps, plus dangling and cycle warnings
  - scope_for: deterministic sorted list of artefact IDs tagged with subject_id
  - lineage_path: root-to-artefact path string (e.g. "a0043 > a0045 > a0046 > a0047")
  - held_ancestor: nearest ancestor under legal hold via BFS, or None
"""
from __future__ import annotations

from collections import deque

from .contracts import Graph


def build_index(graph: Graph) -> dict:
    """Build index dictionaries for fast lookups and audit warnings for anomalies.

    Returns:
        dict with:
          - "children": dict[str, list[str]] (parent_id -> sorted child artefact_ids)
          - "parents": dict[str, list[str]] (artefact_id -> sorted parent artefact_ids)
          - "ancestors": dict[str, set[str]] (artefact_id -> set of all ancestor artefact_ids)
          - "warnings": list[dict] (dangling parent references, cycles detected)
    """
    children: dict[str, list[str]] = {aid: [] for aid in graph}
    parents: dict[str, list[str]] = {}
    warnings: list[dict] = []

    # 1. Parents and children maps + dangling parent detection
    for aid in sorted(graph.keys()):
        art = graph[aid]
        raw_parents = art.get("parent_ids", [])
        valid_parents: list[str] = []
        for pid in raw_parents:
            if pid not in graph:
                warnings.append({
                    "type": "dangling_parent",
                    "artefact_id": aid,
                    "parent_id": pid,
                    "message": f"Artefact {aid!r} references non-existent parent {pid!r}",
                })
            else:
                valid_parents.append(pid)
                children.setdefault(pid, []).append(aid)
        parents[aid] = sorted(valid_parents)

    for pid in children:
        children[pid].sort()

    # 2. Cycle detection via 3-state DFS (0=unvisited, 1=visiting, 2=visited)
    visit_state: dict[str, int] = {}
    cycle_warnings: list[dict] = []

    def _dfs_cycle(curr: str, stack: list[str]) -> None:
        visit_state[curr] = 1
        stack.append(curr)
        for p in parents.get(curr, []):
            st = visit_state.get(p, 0)
            if st == 1:
                idx = stack.index(p)
                cycle_nodes = stack[idx:] + [p]
                cycle_str = " -> ".join(cycle_nodes)
                cycle_warnings.append({
                    "type": "cycle",
                    "artefact_id": curr,
                    "cycle": cycle_str,
                    "message": f"Cycle detected in lineage for {curr!r}: {cycle_str}",
                })
            elif st == 0:
                _dfs_cycle(p, stack)
        stack.pop()
        visit_state[curr] = 2

    for aid in sorted(graph.keys()):
        if visit_state.get(aid, 0) == 0:
            _dfs_cycle(aid, [])

    warnings.extend(cycle_warnings)

    # 3. All ancestors for each node (cycle-safe BFS upwards)
    ancestors: dict[str, set[str]] = {}
    for aid in sorted(graph.keys()):
        node_ancestors: set[str] = set()
        queue = deque(parents.get(aid, []))
        visited = set(queue)
        while queue:
            p = queue.popleft()
            node_ancestors.add(p)
            for gp in parents.get(p, []):
                if gp not in visited:
                    visited.add(gp)
                    queue.append(gp)
        ancestors[aid] = node_ancestors

    return {
        "children": children,
        "parents": parents,
        "ancestors": ancestors,
        "warnings": warnings,
    }


def scope_for(graph: Graph, subject_id: str) -> list[str]:
    """Return sorted artefact IDs associated with subject_id.

    Scope Rule (PLAN_T08 §2.3):
      An artefact belongs to a request's scope if and only if subject_id is in its subject_ids.
      Descending children that belong exclusively to other subjects (Trap B6) are excluded.
    """
    return sorted(aid for aid, a in graph.items() if subject_id in a.get("subject_ids", []))


def lineage_path(graph: Graph, artefact_id: str) -> str:
    """Find root-to-artefact path (e.g. "a0043 > a0045 > a0046 > a0047").

    Uses BFS backwards through parent_ids to find the shortest root-to-node path.
    Ties between parents at the same depth are broken by sorted lexicographical ID.
    If the artefact is already a root or has no parents, returns artefact_id.
    """
    if artefact_id not in graph:
        return str(artefact_id)

    raw_parents = graph[artefact_id].get("parent_ids", [])
    valid_parents = [p for p in raw_parents if p in graph]
    if not valid_parents:
        return str(artefact_id)

    queue: deque[tuple[str, list[str]]] = deque([(artefact_id, [artefact_id])])
    visited: set[str] = {artefact_id}
    best_path: list[str] | None = None
    fallback_path: list[str] = [artefact_id]

    while queue:
        curr, path = queue.popleft()
        fallback_path = path
        curr_parents = [p for p in sorted(graph[curr].get("parent_ids", [])) if p in graph]
        if not curr_parents:
            # Reached a root
            best_path = path
            break
        for p in curr_parents:
            if p not in visited:
                visited.add(p)
                queue.append((p, path + [p]))

    res = best_path if best_path is not None else fallback_path
    return " > ".join(reversed(res))


def held_ancestor(graph: Graph, artefact_id: str) -> str | None:
    """Return legal_hold code of the nearest ancestor under hold, or None.

    Does NOT inspect artefact_id itself (direct hold is handled by policy rule R1).
    Performs BFS upwards starting from the artefact's parents.
    """
    if artefact_id not in graph:
        return None

    initial_parents = sorted(p for p in graph[artefact_id].get("parent_ids", []) if p in graph)
    if not initial_parents:
        return None

    queue: deque[str] = deque(initial_parents)
    visited: set[str] = set(initial_parents)

    while queue:
        curr_id = queue.popleft()
        curr_art = graph[curr_id]
        hold_val = curr_art.get("legal_hold")
        if hold_val:
            return hold_val

        for p in sorted(curr_art.get("parent_ids", [])):
            if p in graph and p not in visited:
                visited.add(p)
                queue.append(p)

    return None


def ancestors_of(graph: Graph, artefact_id: str) -> list[str]:
    """Return sorted list of all ancestor artefact IDs for artefact_id."""
    if artefact_id not in graph:
        return []
    queue = deque(p for p in graph[artefact_id].get("parent_ids", []) if p in graph)
    visited = set(queue)
    ancestors: list[str] = []
    while queue:
        curr = queue.popleft()
        ancestors.append(curr)
        for p in graph[curr].get("parent_ids", []):
            if p in graph and p not in visited:
                visited.add(p)
                queue.append(p)
    return sorted(ancestors)


def descendants_of(graph: Graph, artefact_id: str) -> list[str]:
    """Return sorted list of all descendant artefact IDs for artefact_id."""
    children_map: dict[str, list[str]] = {}
    for aid, a in graph.items():
        for p in a.get("parent_ids", []):
            children_map.setdefault(p, []).append(aid)

    queue = deque(children_map.get(artefact_id, []))
    visited = set(queue)
    descendants: list[str] = []
    while queue:
        curr = queue.popleft()
        descendants.append(curr)
        for ch in children_map.get(curr, []):
            if ch not in visited:
                visited.add(ch)
                queue.append(ch)
    return sorted(descendants)
