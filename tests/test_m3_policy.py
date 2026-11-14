"""M3 policy unit tests; no fixture artefact IDs or legal outcome assertions."""
from pathlib import Path

import shutil

import pytest
import yaml

from src.t08.policy import decide_action

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "configs" / "t08_policy.yaml"
PARAMS = {"policy_file": str(POLICY_PATH), "operator_acl": "data-platform", "hold_scope": "direct"}
REQUEST = {"request_id": "DR-X", "subject_id": "subj-X", "identity_verified": True}
BASE = {"artefact_id": "synthetic-artifact", "subject_ids": ["subj-X"], "acl": ["data-platform"], "origin_known": True, "legal_hold": None}


def test_all_policy_rules_return_configured_decisions():
    cases = [
        ({**BASE, "legal_hold": "LH-X"}, REQUEST, {}, PARAMS, ("retain_legal_hold", "LEGAL_HOLD_ACTIVE", "R1")),
        (BASE, {**REQUEST, "identity_verified": False}, {}, PARAMS, ("escalate", "IDENTITY_UNVERIFIED", "R2")),
        ({**BASE, "acl": ["vendor-x"]}, REQUEST, {}, PARAMS, ("escalate", "NO_DELETE_PERMISSION", "R3")),
        ({**BASE, "origin_known": False}, REQUEST, {}, PARAMS, ("escalate", "UNKNOWN_ORIGIN", "R4")),
        ({**BASE, "subject_ids": ["subj-X", "subj-Y"]}, REQUEST, {}, PARAMS, ("escalate", "MULTI_SUBJECT", "R5")),
        (BASE, REQUEST, {"held_ancestor": "LH-X"}, {**PARAMS, "hold_scope": "descendants"}, ("retain_legal_hold", "DERIVED_FROM_HELD", "R6")),
        (BASE, REQUEST, {}, PARAMS, ("delete", "SUBJECT_ONLY", "R7")),
    ]
    for artefact, request, info, params, expected in cases:
        result = decide_action(artefact, request, info, params)
        assert (result["action"], result["reason_code"], result["rule_id"]) == expected


def test_direct_hold_scope_deletes_derivative_with_review_reason():
    result = decide_action(BASE, REQUEST, {"held_ancestor": "LH-X"}, PARAMS)
    assert (result["action"], result["reason_code"], result["rule_id"]) == ("delete", "DERIVED_FROM_HELD", "R6")
    assert result["score"] > 0


def test_descendant_scope_retains_derivative():
    result = decide_action(BASE, REQUEST, {"held_ancestor": "LH-X"}, {**PARAMS, "hold_scope": "descendants"})
    assert (result["action"], result["reason_code"], result["rule_id"]) == (
        "retain_legal_hold", "DERIVED_FROM_HELD", "R6"
    )


def test_legal_hold_has_precedence_over_other_exceptions():
    result = decide_action(
        {**BASE, "legal_hold": "LH-X", "acl": []},
        {**REQUEST, "identity_verified": False},
        {},
        PARAMS,
    )
    assert (result["action"], result["reason_code"], result["rule_id"]) == (
        "retain_legal_hold", "LEGAL_HOLD_ACTIVE", "R1"
    )


def test_missing_identity_and_permission_fail_closed():
    missing_identity = decide_action(BASE, {"request_id": "DR-X", "subject_id": "subj-X"}, {}, PARAMS)
    missing_acl = decide_action({**BASE, "acl": []}, REQUEST, {}, PARAMS)
    assert (missing_identity["action"], missing_identity["reason_code"]) == ("escalate", "IDENTITY_UNVERIFIED")
    assert (missing_acl["action"], missing_acl["reason_code"]) == ("escalate", "NO_DELETE_PERMISSION")


def test_review_scores_order_direct_hold_derived_exception_and_delete():
    held = decide_action({**BASE, "legal_hold": "LH-X"}, REQUEST, {}, PARAMS)
    derivative = decide_action(BASE, REQUEST, {"held_ancestor": "LH-X"}, PARAMS)
    escalation = decide_action({**BASE, "origin_known": False}, REQUEST, {}, PARAMS)
    ordinary_delete = decide_action(BASE, REQUEST, {}, PARAMS)
    assert held["score"] > derivative["score"] > escalation["score"] > ordinary_delete["score"]


def test_policy_yaml_has_ordered_rules_sources_scores_and_official_links():
    config = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    assert [rule["id"] for rule in config["rules"]] == [f"R{i}" for i in range(1, 8)]
    assert all(rule.get("source") and "TODO" not in rule["source"] for rule in config["rules"])
    assert set(config["review_scores"]) == {"retain_legal_hold", "escalate", "delete_derived_from_held", "delete"}
    assert "https://vanban.chinhphu.vn/?pageid=27160&docid=214590" in config["rules"][0]["source"]
    assert "Điều 14 khoản 2" in config["rules"][0]["source"]
    assert "https://eur-lex.europa.eu/eli/reg/2016/679/art_17/oj/eng" in config["rules"][0]["source"]
    assert "https://vanban.chinhphu.vn/?pageid=27160&docid=214590" in config["rules"][6]["source"]


def test_fixture_policy_counts_match_plan_after_private_line_ending_normalization(tmp_path):
    # Git on this Windows host checked out tracked fixture text as CRLF despite
    # .gitattributes. Normalize copies only; leave original fixture files intact.
    fixture = tmp_path / "fixture"
    shutil.copytree(PROJECT_ROOT / "fixtures" / "t08_deletion", fixture)
    for name in ("data_graph.json", "requests.json"):
        path = fixture / name
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))

    from src.t08 import lineage
    from src.t08.loader import load_inputs

    graph, requests = load_inputs(fixture)
    lineage.build_index(graph)
    rows = []
    for request in requests:
        for artefact_id in lineage.scope_for(graph, request["subject_id"]):
            artefact = graph[artefact_id]
            info = {
                "held_ancestor": lineage.held_ancestor(graph, artefact_id),
                "lineage_path": lineage.lineage_path(graph, artefact_id),
            }
            rows.append((artefact, decide_action(artefact, request, info, PARAMS)))

    assert len(rows) == 158
    assert sum(result["action"] == "delete" for _, result in rows) == 128
    assert sum(result["action"] == "retain_legal_hold" for _, result in rows) == 2
    assert sum(result["action"] == "escalate" for _, result in rows) == 28
    assert all(result["action"] != "delete" for art, result in rows if art.get("legal_hold"))
    assert all(result["action"] == "escalate" for art, result in rows if len(art.get("subject_ids", [])) > 1)
