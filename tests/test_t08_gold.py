"""Black-box tests of the T08 PoC through `python -m src.main`. OWNER: M4. PLAN_T08 §5.

Every test runs the real pipeline (loader -> lineage -> policy -> audit) and checks properties that must hold on
ANY graph, so they also guard against hard-coding. Properties are derived from the input graph inside the test
(its own small BFS, independent of src/t08/lineage.py), not copied from the pipeline.

Two inputs:
  - fixtures/t08_deletion      the lab data (158 in-scope pairs, 6 traps)
  - tests/data/t08_mini        hand-written graph with an answer key (expected_actions*.csv)
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src import main as runner
from src.metrics.tracks import eval_t08

REAL = Path("fixtures/t08_deletion")
MINI = Path("tests/data/t08_mini")
LAB = Path("configs/lab.yaml")
ACTIONS = {"delete", "retain_legal_hold", "escalate"}


# ------------------------------------------------------------------ helpers
def run_poc(out, input_dir=REAL, config=LAB):
    return runner.main(["--config", str(config), "--track", "t08", "--input", str(input_dir), "--output", str(out),
                        "--run-name", "poc", "--offline", "--seed", "42"])


def lab_config(tmp_path, **params):
    """lab.yaml with some params overridden (e.g. hold_scope=descendants); track_config made absolute."""
    cfg = yaml.safe_load(LAB.read_text(encoding="utf-8"))
    cfg["track_config"] = str((LAB.parent / cfg["track_config"]).resolve())
    cfg.setdefault("params", {}).update(params)
    p = tmp_path / "lab_variant.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


def load(input_dir):
    graph = {a["artefact_id"]: a for a in json.loads((input_dir / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]}
    reqs = json.loads((input_dir / "requests.json").read_text(encoding="utf-8"))
    return graph, reqs


def in_scope(graph, reqs):
    """The rule from PLAN_T08 §2.3: (request, artefact) iff request.subject_id is in artefact.subject_ids."""
    return {(r["request_id"], aid) for r in reqs for aid, a in graph.items() if r["subject_id"] in a["subject_ids"]}


def descendants(graph, roots):
    kids = defaultdict(list)
    for aid, a in graph.items():
        for p in a["parent_ids"]:
            kids[p].append(aid)
    seen, stack = set(), list(roots)
    while stack:
        x = stack.pop()
        if x not in seen:
            seen.add(x)
            stack += kids[x]
    return seen


@pytest.fixture(scope="module", params=["real", "mini"])
def poc(request, tmp_path_factory):
    """(graph, requests, actions DataFrame, output dir) for each input."""
    d = REAL if request.param == "real" else MINI
    out = tmp_path_factory.mktemp(f"poc_{request.param}")
    assert run_poc(out, d) == 0
    graph, reqs = load(d)
    return graph, reqs, pd.read_csv(out / "actions.csv"), out


# ------------------------------------------------------------------ contract
def test_actions_unique_and_valid(poc):
    graph, reqs, actions, _ = poc
    assert list(actions.columns[:3]) == ["request_id", "artefact_id", "action"]
    assert not actions.duplicated(["request_id", "artefact_id"]).any()
    assert set(actions.action) <= ACTIONS
    assert actions.equals(actions.sort_values(["request_id", "artefact_id"], kind="mergesort").reset_index(drop=True)), "rows must be sorted"


def test_scope_is_exactly_subject_membership(poc):
    """No row for an artefact that does not carry the requester's subject, and none missing."""
    graph, reqs, actions, _ = poc
    assert set(zip(actions.request_id, actions.artefact_id)) == in_scope(graph, reqs)


def test_scope_excludes_other_subjects_trap_b6(poc):
    """Trap B6: descendants of an in-scope artefact that belong only to someone else must get no row.
    A naive BFS over the lineage would delete them; the test proves such artefacts exist and are untouched."""
    graph, reqs, actions, _ = poc
    rows = set(zip(actions.request_id, actions.artefact_id))
    leaked = 0
    naive_extra = 0
    for r in reqs:
        scope = {aid for aid, a in graph.items() if r["subject_id"] in a["subject_ids"]}
        extra = descendants(graph, scope) - scope
        naive_extra += len(extra)
        leaked += sum((r["request_id"], aid) in rows for aid in extra)
    assert naive_extra > 0, "input must contain the trap, otherwise this test proves nothing"
    assert leaked == 0


# ------------------------------------------------------------------ policy outcomes, derived from the graph
def _merged(poc):
    graph, reqs, actions, _ = poc
    req = {r["request_id"]: r for r in reqs}
    a = actions.copy()
    a["hold"] = a.artefact_id.map(lambda i: graph[i]["legal_hold"])
    a["n_subjects"] = a.artefact_id.map(lambda i: len(graph[i]["subject_ids"]))
    a["origin_known"] = a.artefact_id.map(lambda i: graph[i]["origin_known"])
    a["has_permission"] = a.artefact_id.map(lambda i: "data-platform" in graph[i]["acl"])
    a["verified"] = a.request_id.map(lambda i: req[i]["identity_verified"])
    return a


def test_legal_hold_never_deleted(poc):
    a = _merged(poc)
    held = a[a.hold.notna()]
    assert len(held) > 0
    assert set(held.action) == {"retain_legal_hold"}


def test_multi_subject_never_deleted(poc):
    a = _merged(poc)
    shared = a[(a.n_subjects > 1) & a.hold.isna()]
    assert len(shared) > 0
    assert set(shared.action) == {"escalate"}


def test_unknown_origin_and_no_permission_escalated(poc):
    a = _merged(poc)
    risky = a[(~a.origin_known | ~a.has_permission) & a.hold.isna()]
    assert len(risky) > 0
    assert set(risky.action) == {"escalate"}


def test_unverified_identity_never_deleted(poc):
    """Rule R2 sits after the legal hold (R1): an unverified requester gets escalate, except held items."""
    a = _merged(poc)
    unverified = a[~a.verified]
    if unverified.empty:
        pytest.skip("no unverified request in this input (the mini graph covers it)")
    assert set(unverified[unverified.hold.isna()].action) == {"escalate"}
    assert set(unverified[unverified.hold.notna()].action) <= {"retain_legal_hold"}


def test_delete_only_when_every_exception_check_passes(poc):
    """Conversely: a delete implies verified, permitted, known origin, single subject, no direct hold."""
    a = _merged(poc)
    d = a[a.action == "delete"]
    assert len(d) > 0
    assert d.verified.all() and d.has_permission.all() and d.origin_known.all()
    assert (d.n_subjects == 1).all() and d.hold.isna().all()


# ------------------------------------------------------------------ audit
def test_audit_covers_every_action(poc):
    """The grader counts an action as audited iff an audit entry has item_id == artefact_id."""
    _, _, actions, out = poc
    log = [json.loads(l) for l in (out / "audit_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    logged = {e["item_id"] for e in log}
    assert set(actions.artefact_id) <= logged
    per_pair = {(e["extra"].get("request_id"), e["item_id"]) for e in log if e["extra"].get("request_id")}
    assert set(zip(actions.request_id, actions.artefact_id)) <= per_pair, "every (request, artefact) pair needs its own entry"


def test_every_decision_has_reason_and_owner(poc):
    _, _, actions, out = poc
    assert actions.reason.notna().all() and (actions.reason.astype(str).str.len() > 0).all()
    dec = json.loads((out / "decision.json").read_text(encoding="utf-8"))
    assert dec["owner"].strip() and dec["reason_code"].strip() and dec["status"] in {"GO", "HOLD", "REWORK"}


# ------------------------------------------------------------------ reproducibility
def test_idempotent_two_runs(tmp_path):
    """Two clean runs and a re-run over an existing output folder all give the same actions.csv."""
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    a, b = tmp_path / "a", tmp_path / "b"
    assert run_poc(a) == 0 and run_poc(b) == 0
    assert sha(a / "actions.csv") == sha(b / "actions.csv")
    assert run_poc(a) == 0                                  # again, same folder (audit log appends)
    assert sha(a / "actions.csv") == sha(b / "actions.csv")


# ------------------------------------------------------------------ failure modes
@pytest.mark.parametrize("breakage", ["bad_json", "missing_field", "missing_file", "duplicate_artefact", "tampered_manifest"])
def test_bad_input_fails_loudly(tmp_path, breakage):
    """Broken input exits 2 and never leaves a plausible-looking actions.csv behind.
    Provenance is switched off except in the tampered_manifest case, so the loader's own checks are what fail."""
    d, out = tmp_path / "in", tmp_path / "out"
    d.mkdir()
    graph = json.loads((MINI / "data_graph.json").read_text(encoding="utf-8"))
    reqs = (MINI / "requests.json").read_text(encoding="utf-8")
    strict = False
    if breakage == "bad_json":
        (d / "data_graph.json").write_text("{not json", encoding="utf-8")
        (d / "requests.json").write_text(reqs, encoding="utf-8")
    elif breakage == "missing_field":
        del graph["artefacts"][0]["subject_ids"]
        (d / "data_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (d / "requests.json").write_text(reqs, encoding="utf-8")
    elif breakage == "duplicate_artefact":
        graph["artefacts"].append(dict(graph["artefacts"][0]))
        (d / "data_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (d / "requests.json").write_text(reqs, encoding="utf-8")
    elif breakage == "missing_file":                       # requests.json absent
        (d / "data_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    else:                                                  # valid data, but it no longer matches manifest.csv
        strict = True
        (d / "manifest.csv").write_text((MINI / "manifest.csv").read_text(encoding="utf-8"), encoding="utf-8")
        (d / "requests.json").write_text(reqs, encoding="utf-8")
        graph["artefacts"][0]["created_at"] = "1999-01-01"
        (d / "data_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    cfg = lab_config(tmp_path)
    cfg_data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    cfg_data["strict_provenance"] = strict
    cfg.write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
    assert run_poc(out, d, cfg) == 2
    assert not (out / "actions.csv").exists()


# ------------------------------------------------------------------ gold answers (mini graph)
def _compare(actions, gold_name):
    gold = pd.read_csv(MINI / gold_name)
    m = gold.merge(actions, on=["request_id", "artefact_id"], how="outer", indicator=True)
    assert (m._merge == "both").all(), m[m._merge != "both"][["request_id", "artefact_id", "_merge"]].to_dict("records")
    bad = m[(m.expected_action != m.action) | (m.expected_reason != m.reason)]
    assert bad.empty, bad[["request_id", "artefact_id", "expected_action", "action", "expected_reason", "reason"]].to_dict("records")


def test_mini_gold_exact_match(tmp_path):
    """PoC output equals the hand-written answers, action AND reason_code, on all 18 rows (hold_scope=direct)."""
    assert run_poc(tmp_path, MINI) == 0
    _compare(pd.read_csv(tmp_path / "actions.csv"), "expected_actions.csv")


def test_mini_gold_exact_match_descendants_ablation(tmp_path):
    """Same graph with hold_scope=descendants equals the second answer key; it differs from direct on held-derived rows only."""
    assert run_poc(tmp_path / "desc", MINI, lab_config(tmp_path, hold_scope="descendants")) == 0
    desc = pd.read_csv(tmp_path / "desc" / "actions.csv")
    _compare(desc, "expected_actions_descendants.csv")
    assert run_poc(tmp_path / "direct", MINI) == 0
    direct = pd.read_csv(tmp_path / "direct" / "actions.csv")
    diff = direct.merge(desc, on=["request_id", "artefact_id"], suffixes=("_d", "_x"))
    diff = diff[diff.action_d != diff.action_x]
    assert len(diff) > 0 and set(diff.reason_d) == {"DERIVED_FROM_HELD"} and set(diff.action_d) == {"delete"} and set(diff.action_x) == {"retain_legal_hold"}


def test_mini_graph_dangling_parent_holds_the_decision(tmp_path):
    """The mini graph has a parent_ids entry pointing nowhere: actions are still produced, but decide() must HOLD."""
    assert run_poc(tmp_path, MINI) == 0
    dec = json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))
    assert dec["status"] == "HOLD" and dec["reason_code"] == "DATA_WARNINGS"
    log = [json.loads(l) for l in (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(e["action"] == "data_warning" for e in log)


def test_mini_scores_with_official_evaluator(tmp_path):
    """Feed the mini answer key through the lab's own eval_t08: completeness 1.0, false-delete 0, audit 1.0."""
    assert run_poc(tmp_path, MINI) == 0
    gold = pd.read_csv(MINI / "expected_actions.csv")[["request_id", "artefact_id", "expected_action"]]
    gt_path = tmp_path / "gold_for_eval.csv"
    gold.to_csv(gt_path, index=False)
    res = {m.name: m.value for m in eval_t08(gt_path, tmp_path / "actions.csv", {}).metrics}
    assert res["Deletion Completeness"] == 1.0
    assert res["False-delete count"] == 0
    assert res["Exception handling accuracy"] == 1.0
    assert res["Audit trace completeness"] == 1.0
