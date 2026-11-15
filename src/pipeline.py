"""T08 PoC pipeline — wiring only. OWNER: M1. Logic lives in src/t08/ (see CONTRIBUTING.md).

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)              -> t08.loader   (M2)
    02 process   scope + lineage + policy for every (request, artefact) -> t08.lineage (M2), t08.policy (M3)
    03 rank      review queue top-B (exceptions first)                -> here (M1)
    04 review    reviewer overrides + audit log                       -> t08.audit    (M5)
    05 decide    GO / HOLD with reason_code + owner                   -> here (M1)

Output: out/actions.csv (request_id, artefact_id, action) + audit_log.jsonl + review_queue.csv + decision.json.
Rules: never read fixtures/*/gt/; no network; no hard-coded artefact ids (graded on a hidden set).
"""
from __future__ import annotations

import sys

import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track
from .t08 import audit, dashboard, lineage, loader, policy
from .t08.contracts import ACTIONS, SCORED_COLUMNS, item_id


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    graph, requests = loader.load_inputs(ctx.input_dir)
    index = lineage.build_index(graph)
    for w in index.get("warnings", []):
        ctx.audit.log(actor="pipeline", action="data_warning", item_id=str(w.get("artefact_id", "")), after=w)
    ctx.stats.update(n_artefacts=len(graph), n_requests=len(requests), n_data_warnings=len(index.get("warnings", [])))
    return {"graph": graph, "requests": requests, "index": index}


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    graph, params = data["graph"], ctx.config.get("params") or {}
    rows = []
    for req in data["requests"]:
        for aid in lineage.scope_for(graph, req["subject_id"]):
            art = graph[aid]
            info = {"held_ancestor": lineage.held_ancestor(graph, aid), "lineage_path": lineage.lineage_path(graph, aid)}
            d = policy.decide_action(art, req, info, params)
            if d["action"] not in ACTIONS:
                raise ValueError(f"policy returned invalid action {d['action']!r} for {req['request_id']}/{aid}")
            rows.append({
                "request_id": req["request_id"], "artefact_id": aid, "action": d["action"],
                "item_id": item_id(req["request_id"], aid), "score": float(d["score"]),
                "reason": d["reason_code"], "rule_id": d["rule_id"],
                "type": art.get("type", ""), "subject_ids": ";".join(art.get("subject_ids", [])),
                "lineage_path": info["lineage_path"], "held_ancestor": info["held_ancestor"] or "",
                "deadline": req.get("deadline", ""),
            })
    df = pd.DataFrame(rows, columns=SCORED_COLUMNS)
    if df.duplicated(["request_id", "artefact_id"]).any():
        raise ValueError("duplicate (request_id, artefact_id) rows — scope_for must return unique ids")
    return df.sort_values(["request_id", "artefact_id"], kind="mergesort").reset_index(drop=True)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Top-B by score; ties broken by nearer deadline, then id (deterministic)."""
    budget = int(ctx.param("budget", 60))
    ordered = scored.sort_values(["score", "deadline", "item_id"], ascending=[False, True, True], kind="mergesort")
    q = make_review_queue(ordered, id_col="item_id", score_col="score", budget=budget,
                          reason_col="reason", action_col="action", slice_col="type")
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(q, ctx.out("contact_sheet.html"), image_col=None,
                         title=f"T08 · Hàng chờ duyệt yêu cầu xóa (B={budget})")
    ctx.stats["n_queue"] = len(q)
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    reviewed = load_review_decisions(reviewed_path) if reviewed_path.exists() else None
    ctx.stats["n_reviewed"] = 0 if reviewed is None else len(reviewed)
    final = audit.apply_review(ctx, scored, reviewed)
    audit.write_audit(ctx, final)
    reviewed_ids = set() if reviewed is None else set(reviewed["item_id"].astype(str))
    ctx.stats["n_pending_review"] = int(((final["action"] == "escalate") & ~final["item_id"].isin(reviewed_ids)).sum())
    return final


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    owner = ctx.config.get("owner", "TODO-owner")
    counts = final["action"].value_counts().to_dict()
    pending = int(ctx.stats.get("n_pending_review", (final["action"] == "escalate").sum()))
    if ctx.stats.get("n_data_warnings", 0):
        return Decision(status="HOLD", reason_code="DATA_WARNINGS", owner=owner, scope=ctx.track, metrics=counts,
                        reason=f"{ctx.stats['n_data_warnings']} lineage/data warnings must be resolved before deleting")
    if pending > 0:
        return Decision(status="HOLD", reason_code="ESCALATIONS_PENDING_REVIEW", owner=owner, scope=ctx.track, metrics=counts,
                        reason=f"{pending} escalated item(s) still need a human decision")
    return Decision(status="GO", reason_code="ALL_ITEMS_RESOLVED", owner=owner, scope=ctx.track, metrics=counts,
                    reason="Every in-scope artefact has a final action; exceptions reviewed")


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    if spec.track != "t08":
        raise NotImplementedError(f"this group's pipeline implements t08 only, not {spec.track}")
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    extra = [c for c in final.columns if c not in spec.pred_columns]
    final[spec.pred_columns + extra].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
    _render_demo(ctx, final, data)


def _render_demo(ctx: RunContext, final: pd.DataFrame, data: dict) -> None:
    """Demo console (docs/PLAN_DEMO_T08.md). Never allowed to break the graded run."""
    try:
        path = dashboard.render_dashboard(ctx, final, data)
        ctx.stats["dashboard"] = str(path)
    except Exception as e:  # noqa: BLE001 — the dashboard is optional; actions.csv is already written
        ctx.audit.log(actor="pipeline", action="dashboard_failed", item_id="dashboard.html", reason=repr(e))
        print(f"[pipeline] WARNING: dashboard not generated: {e!r}", file=sys.stderr)
