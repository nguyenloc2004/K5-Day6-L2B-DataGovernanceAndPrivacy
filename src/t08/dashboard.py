"""Offline DSR console (demo): one self-contained HTML page built from this run's outputs. OWNER: M1.

Shows only what the pipeline already produced (actions, review queue, audit log, decision, run info)
plus the input graph. It adds no decision logic, so it cannot change the graded actions.csv.
No network: no CDN, no web fonts; data is embedded as JSON in the page.

See docs/PLAN_DEMO_T08.md.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from ..common.io import git_sha
from ..common.review import load_review_decisions

TEMPLATE = Path(__file__).with_name("templates") / "dashboard.html"
PLACEHOLDER = "/*__DSR_DATA__*/null"

# Layout of the lineage tree (pixels, left-to-right by depth).
COL_W, ROW_H, NODE_W, NODE_H, PAD = 190, 46, 160, 34, 16
MAX_CONTEXT_PARENTS = 2   # draw out-of-scope parents only for nodes with few parents (exports have 12)


# ------------------------------------------------------------------ helpers
def _reviewed_ids(output_dir: Path) -> dict[str, dict]:
    """item_id -> reviewer row, read from review_queue_reviewed.csv if present."""
    path = output_dir / "review_queue_reviewed.csv"
    if not path.exists():
        return {}
    df = load_review_decisions(path)
    return {str(r["item_id"]): {"reviewer": r["reviewer"], "decision": r["reviewer_decision"],
                                "override": r["override_value"], "note": r["review_note"]}
            for _, r in df.iterrows()}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def _days_left(deadline: str, as_of: date) -> int | None:
    try:
        return (datetime.fromisoformat(str(deadline)).date() - as_of).days
    except ValueError:
        return None


def _flags(art: dict, operator_acl: str) -> list[str]:
    f = []
    if art.get("legal_hold"):
        f.append("hold")
    if len(art.get("subject_ids", [])) > 1:
        f.append("multi")
    if art.get("origin_known") is not True:
        f.append("unknown_origin")
    if operator_acl not in (art.get("acl") or []):
        f.append("no_acl")
    return f


# ------------------------------------------------------------------ tree
def build_tree(graph: dict, rows: pd.DataFrame, subject_id: str, operator_acl: str) -> dict:
    """Nodes/edges for one request with x/y already laid out.

    status per node: an action (delete / retain_legal_hold / escalate) for in-scope artefacts,
    "context" for an out-of-scope parent (shown so the root is visible),
    "out_of_scope" for an out-of-scope child of an in-scope node (trap B6: someone else's data).
    """
    by_id = {r.artefact_id: r for r in rows.itertuples(index=False)}
    in_scope = set(by_id)
    shown: dict[str, str] = {aid: by_id[aid].action for aid in in_scope}
    hidden_parents: dict[str, int] = {}

    for aid in sorted(in_scope):
        parents = [p for p in graph[aid].get("parent_ids", []) if p in graph]
        outside = [p for p in parents if p not in in_scope]
        if len(parents) <= MAX_CONTEXT_PARENTS:
            for p in outside:
                shown.setdefault(p, "context")
        elif outside:
            hidden_parents[aid] = len(outside)
    children: dict[str, list[str]] = {}
    for a in graph.values():
        for p in a.get("parent_ids", []):
            children.setdefault(p, []).append(a["artefact_id"])
    # Out-of-scope descendants hanging under in-scope nodes (trap B6), followed down their branch.
    frontier = sorted(in_scope)
    while frontier:
        nxt = []
        for aid in frontier:
            for c in sorted(children.get(aid, [])):
                if c in shown or subject_id in graph[c].get("subject_ids", []):
                    continue
                shown[c] = "out_of_scope"
                nxt.append(c)
        frontier = nxt

    edges = sorted((p, aid) for aid in shown for p in graph[aid].get("parent_ids", []) if p in shown)
    parents_of: dict[str, list[str]] = {}
    kids_of: dict[str, list[str]] = {}
    for p, c in edges:
        parents_of.setdefault(c, []).append(p)
        kids_of.setdefault(p, []).append(c)

    # depth = longest path from a displayed root (graph is a DAG; guard against cycles)
    depth: dict[str, int] = {}

    def _depth(n: str, seen: frozenset) -> int:
        if n in depth:
            return depth[n]
        ps = [p for p in parents_of.get(n, []) if p not in seen]
        depth[n] = 0 if not ps else 1 + max(_depth(p, seen | {n}) for p in ps)
        return depth[n]

    for n in sorted(shown):
        _depth(n, frozenset())

    # tidy layout: DFS over a spanning tree (first parent wins), leaves get consecutive rows,
    # a parent sits at the mean row of its children.
    tree_parent = {n: sorted(parents_of[n], key=lambda p: (-depth[p], p))[0] for n in shown if parents_of.get(n)}
    tree_kids: dict[str, list[str]] = {}
    for n, p in tree_parent.items():
        tree_kids.setdefault(p, []).append(n)
    type_order = {"raw_video": 0, "backup": 1, "frame": 2, "face_crop": 3, "annotation": 4,
                  "embedding": 5, "training_export": 6}
    for p in tree_kids:
        tree_kids[p].sort(key=lambda n: (type_order.get(graph[n].get("type"), 9), n))
    row: dict[str, float] = {}
    next_row = [0]

    def _place(n: str) -> float:
        ks = tree_kids.get(n, [])
        if not ks:
            row[n] = next_row[0]
            next_row[0] += 1
        else:
            ys = [_place(k) for k in ks]
            row[n] = sum(ys) / len(ys)
        return row[n]

    for root in sorted((n for n in shown if n not in tree_parent), key=lambda n: (depth[n], n)):
        _place(root)

    nodes = []
    for aid in sorted(shown, key=lambda n: (depth[n], row[n])):
        art, r = graph[aid], by_id.get(aid)
        nodes.append({
            "id": aid, "type": art.get("type", ""), "status": shown[aid],
            "x": PAD + depth[aid] * COL_W, "y": PAD + row[aid] * ROW_H,
            "subject_ids": art.get("subject_ids", []), "uri": art.get("uri", ""),
            "acl": art.get("acl", []), "owner": art.get("owner", ""), "legal_hold": art.get("legal_hold"),
            "origin_known": art.get("origin_known"), "flags": _flags(art, operator_acl),
            "reason": getattr(r, "reason", "") if r is not None else "",
            "rule_id": getattr(r, "rule_id", "") if r is not None else "",
            "held_ancestor": (getattr(r, "held_ancestor", "") or "") if r is not None else "",
            "lineage_path": getattr(r, "lineage_path", "") if r is not None else "",
            "hidden_parents": hidden_parents.get(aid, 0),
        })
    width = PAD * 2 + (max(depth.values(), default=0)) * COL_W + NODE_W
    height = PAD * 2 + max(next_row[0], 1) * ROW_H
    return {"nodes": nodes, "edges": [list(e) for e in edges], "width": width, "height": height,
            "node_w": NODE_W, "node_h": NODE_H}


# ------------------------------------------------------------------ payload
def build_payload(ctx, final: pd.DataFrame, data: dict) -> dict:
    graph, requests = data["graph"], data["requests"]
    operator_acl = str(ctx.param("operator_acl", "data-platform"))
    dry_run = bool(ctx.param("dry_run", True))
    as_of = date.today()
    reviewed = _reviewed_ids(ctx.output_dir)
    final = final.copy()
    final["held_ancestor"] = final["held_ancestor"].fillna("") if "held_ancestor" in final else ""

    req_out, trees = [], {}
    for req in requests:
        rid, sid = req["request_id"], req["subject_id"]
        rows = final[final.request_id == rid]
        counts = {a: int((rows.action == a).sum()) for a in ("delete", "retain_legal_hold", "escalate")}
        pending = int(sum(1 for r in rows.itertuples(index=False) if r.action == "escalate" and r.item_id not in reviewed))
        if req.get("identity_verified") is not True:
            status = "unverified"
        elif pending:
            status = "pending_review"
        elif dry_run:
            status = "ready"
        else:
            status = "executed"
        req_out.append({**{k: req.get(k) for k in ("request_id", "subject_id", "received_at", "deadline",
                                                   "channel", "identity_verified")},
                        "days_left": _days_left(req.get("deadline", ""), as_of),
                        "counts": counts, "pending": pending, "n_items": int(len(rows)), "status": status,
                        "derived_from_held": int((rows.reason == "DERIVED_FROM_HELD").sum())})
        trees[rid] = build_tree(graph, rows, sid, operator_acl)

    keep = ["request_id", "artefact_id", "action", "item_id", "reason", "rule_id", "type",
            "subject_ids", "lineage_path", "held_ancestor", "deadline"]
    rows_out = final[[c for c in keep if c in final.columns]].astype(str).to_dict(orient="records")
    for r in rows_out:
        rv = reviewed.get(r["item_id"])
        r["review"] = rv or None

    out = ctx.output_dir
    run_info = _read_json(out / "run_info.json") or {}
    reports = Path("reports")
    metrics = {k: _read_json(reports / f"metrics_{k}.json") for k in ("baseline", "poc")}
    baseline_counts = None
    base_actions = out.parent / "baseline" / "actions.csv"
    if base_actions.exists():
        try:
            b = pd.read_csv(base_actions)
            baseline_counts = {"n_rows": int(len(b)), **{a: int((b.action == a).sum())
                                                         for a in ("delete", "retain_legal_hold", "escalate")}}
        except (OSError, ValueError, KeyError):
            baseline_counts = None

    return {
        "run": {"track": ctx.track, "run_name": ctx.run_name, "seed": ctx.seed, "offline": ctx.offline,
                "dry_run": dry_run, "hold_scope": ctx.param("hold_scope", "direct"),
                "budget": int(ctx.param("budget", 60)), "git_sha": git_sha(), "as_of": as_of.isoformat(),
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "input": str(ctx.input_dir), "n_artefacts": len(graph), "owner": ctx.config.get("owner", ""),
                "group_id": ctx.config.get("group_id", ""), "stats": ctx.stats,
                "runtime_seconds": run_info.get("runtime_seconds")},
        "decision": _read_json(out / "decision.json") or {},
        "requests": req_out,
        "rows": rows_out,
        "trees": trees,
        "queue": pd.read_csv(out / "review_queue.csv", dtype=str).fillna("").to_dict(orient="records")
        if (out / "review_queue.csv").exists() else [],
        "audit": _read_jsonl(out / "audit_log.jsonl")[-3000:],
        "metrics": metrics,
        "baseline_counts": baseline_counts,
        "has_contact_sheet": (out / "contact_sheet.html").exists(),
    }


def render_dashboard(ctx, final: pd.DataFrame, data: dict) -> Path:
    payload = build_payload(ctx, final, data)
    blob = json.dumps(payload, ensure_ascii=False, default=str).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in page:
        raise ValueError(f"dashboard template {TEMPLATE} has no data placeholder")
    path = ctx.out("dashboard.html")
    path.write_text(page.replace(PLACEHOLDER, blob), encoding="utf-8")
    return path
