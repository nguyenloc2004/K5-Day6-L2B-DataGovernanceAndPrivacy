"""Integrity of the hand-written mini gold set (tests/data/t08_mini). OWNER: M4.

These tests check the DATA, not the pipeline: they fail if someone edits the graph or the answers
and breaks the set's promises (every trap present, answers well-formed, hashes intact).
Pipeline-vs-gold tests live in test_t08_gold.py (needs M2/M3 code).
"""
import json
from pathlib import Path

import pandas as pd

from src.common.manifest import verify_manifest
from src.t08.contracts import ACTIONS

MINI = Path("tests/data/t08_mini")
REAL = Path("fixtures/t08_deletion")
REASONS = {"LEGAL_HOLD_ACTIVE", "IDENTITY_UNVERIFIED", "NO_DELETE_PERMISSION", "UNKNOWN_ORIGIN",
           "MULTI_SUBJECT", "DERIVED_FROM_HELD", "SUBJECT_ONLY"}
OPERATOR = "data-platform"


def _graph():
    return {a["artefact_id"]: a for a in json.loads((MINI / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]}


def _requests():
    return json.loads((MINI / "requests.json").read_text(encoding="utf-8"))


def _gold(name="expected_actions.csv"):
    return pd.read_csv(MINI / name)


def test_mini_manifest_hashes_match():
    assert verify_manifest(MINI / "manifest.csv") == []


def test_mini_ids_do_not_collide_with_real_fixture():
    real = {a["artefact_id"] for a in json.loads((REAL / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]}
    assert not real & set(_graph()), "mini ids must differ from the lab fixture to catch hard-coding"
    real_subj = {r["subject_id"] for r in json.loads((REAL / "requests.json").read_text(encoding="utf-8"))}
    assert not real_subj & {r["subject_id"] for r in _requests()}


def test_mini_gold_is_well_formed():
    graph, reqs = _graph(), _requests()
    for name in ("expected_actions.csv", "expected_actions_descendants.csv"):
        g = _gold(name)
        assert not g.duplicated(["request_id", "artefact_id"]).any(), name
        assert set(g.expected_action) <= set(ACTIONS), name
        assert set(g.expected_reason) <= REASONS, name
        assert set(g.request_id) == {r["request_id"] for r in reqs}, name
        assert set(g.artefact_id) <= set(graph), name


def test_mini_gold_scope_is_exactly_subject_membership():
    """Gold rows == every (request, artefact tagged with the request's subject). No more, no fewer."""
    graph = _graph()
    want = {(r["request_id"], aid) for r in _requests() for aid, a in graph.items() if r["subject_id"] in a["subject_ids"]}
    for name in ("expected_actions.csv", "expected_actions_descendants.csv"):
        g = _gold(name)
        assert set(zip(g.request_id, g.artefact_id)) == want, name


def test_mini_gold_covers_every_action_and_rule():
    g = _gold()
    assert set(g.expected_action) == set(ACTIONS)
    assert set(g.expected_reason) == REASONS                                   # direct mode exercises every rule
    held = g[g.expected_reason == "DERIVED_FROM_HELD"]
    assert set(held.expected_action) == {"delete"}                             # Q1 direct: derivative is deleted, flagged for review
    d = _gold("expected_actions_descendants.csv")
    assert set(d[d.expected_reason == "DERIVED_FROM_HELD"].expected_action) == {"retain_legal_hold"}   # ablation: hold propagates
    changed = g.merge(d, on=["request_id", "artefact_id"], suffixes=("_direct", "_desc"))
    changed = changed[changed.expected_action_direct != changed.expected_action_desc]
    assert set(changed.artefact_id) == set(held.artefact_id), "the two modes must differ exactly on held-derived rows"


def test_mini_graph_contains_each_trap():
    graph, reqs = _graph(), _requests()
    held = {i for i, a in graph.items() if a["legal_hold"]}
    assert held, "B1 legal hold"
    assert any(a["parent_ids"] and set(a["parent_ids"]) & held and not a["legal_hold"] for a in graph.values()), "B2 child of held"
    assert any(not a["origin_known"] for a in graph.values()), "B3 unknown origin"
    assert any(OPERATOR not in a["acl"] for a in graph.values()), "B4 no permission"
    assert any(len(a["subject_ids"]) > 1 for a in graph.values()), "B5 multi-subject"
    # B6: a child of a multi-subject artefact whose own subjects are not all in the parent's requester set
    b6 = [i for i, a in graph.items() for p in a["parent_ids"]
          if p in graph and len(graph[p]["subject_ids"]) > 1 and len(a["subject_ids"]) == 1]
    assert b6, "B6 single-subject child of a shared artefact"
    assert any(not r["identity_verified"] for r in reqs), "unverified identity"
    assert any(p not in graph for a in graph.values() for p in a["parent_ids"]), "dangling parent"
    requested = {r["subject_id"] for r in reqs}
    assert any(not set(a["subject_ids"]) & requested for a in graph.values()), "artefact nobody asked to delete"
