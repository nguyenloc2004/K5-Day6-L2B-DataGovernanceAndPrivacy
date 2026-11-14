"""Baseline (PLAN_T08 §2.4): delete only the raw video found by filename, no lineage. OWNER: M4.

This is the bar the PoC must beat. It is deliberately naive and shares NOTHING with the PoC
(own JSON reading, no loader/lineage/policy), so a bug in M2/M3 cannot move the baseline's numbers.

What it does, per request:
  - find `raw_video` artefacts whose `filename` names the requester's subject_id
  - mark each one `delete`
What it never does (these are its measured weaknesses):
  - look at derived data: frames, face crops, embeddings, backups, exports  -> low Completeness
  - look at `legal_hold`, `acl`, `origin_known` or other subjects             -> false deletes on held videos

Artefacts without a `filename` fall back to `subject_ids` so the baseline still runs on graphs that
omit filenames (e.g. tests/data/t08_mini). No artefact id is written anywhere in this file.

Run:
    python -m src.main --track t08 --pipeline src.t08.baseline --output out/baseline --run-name baseline --offline --seed 42

Nothing is deleted for real: the output is a plan (actions.csv) plus an audit entry per row.
The audit log is append-only, so clear out/baseline before a run you want to report.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from ..common.decision import Decision, write_decision
from ..metrics.tracks import get_track

RAW_TYPE = "raw_video"


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name} is not valid JSON: {e}") from e


def _load(ctx) -> tuple[list[dict], list[dict]]:
    raw = _read_json(ctx.input_dir / "data_graph.json")
    requests = _read_json(ctx.input_dir / "requests.json")
    if not isinstance(raw, dict) or not isinstance(raw.get("artefacts"), list):
        raise ValueError("data_graph.json must be an object with an 'artefacts' list")
    if not isinstance(requests, list):
        raise ValueError("requests.json must be a list of requests")
    seen = set()
    for a in raw["artefacts"]:
        for key in ("artefact_id", "type"):
            if key not in a:
                raise ValueError(f"artefact missing required field {key!r}: {a}")
        if a["artefact_id"] in seen:
            raise ValueError(f"duplicate artefact_id {a['artefact_id']!r}")
        seen.add(a["artefact_id"])
    for r in requests:
        for key in ("request_id", "subject_id"):
            if key not in r:
                raise ValueError(f"request missing required field {key!r}: {r}")
    return raw["artefacts"], requests


def _names_subject(artefact: dict, subject_id: str) -> bool:
    """Does this raw video belong to `subject_id`? Filename first, subject_ids only if there is no filename."""
    filename = artefact.get("filename")
    if filename:
        # whole-token match: "subj_1" must not match "subj_10"
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(subject_id)}(?![A-Za-z0-9])", filename) is not None
    return subject_id in artefact.get("subject_ids", [])


def run(ctx) -> None:
    spec = get_track(ctx.track)
    artefacts, requests = _load(ctx)
    rows = []
    for req in requests:
        for a in artefacts:
            if a["type"] == RAW_TYPE and _names_subject(a, req["subject_id"]):
                rows.append({"request_id": req["request_id"], "artefact_id": a["artefact_id"], "action": "delete"})
    df = pd.DataFrame(rows, columns=spec.pred_columns)
    if df.duplicated(["request_id", "artefact_id"]).any():
        raise ValueError("duplicate (request_id, artefact_id) rows: request_ids must be unique")
    df = df.sort_values(["request_id", "artefact_id"], kind="mergesort").reset_index(drop=True)

    for r in df.itertuples(index=False):
        ctx.audit.log(actor="baseline", action="delete", item_id=r.artefact_id,
                      reason="raw_video_filename_match", request_id=r.request_id, dry_run=True)
    ctx.stats.update(n_artefacts=len(artefacts), n_requests=len(requests), n_items=len(df))
    df.to_csv(ctx.out(spec.pred_file), index=False)

    write_decision(
        Decision(status="HOLD", reason_code="BASELINE_ONLY",
                 reason="Naive baseline: deletes raw videos only, ignores legal hold, permissions and derived data. Never release on this.",
                 owner=ctx.config.get("owner", "baseline"), scope=ctx.track,
                 evidence=[str(ctx.out(spec.pred_file))], metrics={"delete": len(df)}),
        ctx.out("decision.json"), ctx.out("decision_log.csv"))
