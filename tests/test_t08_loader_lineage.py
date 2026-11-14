"""Unit tests for T08 loader and lineage modules. OWNER: M2."""
import json
from pathlib import Path
import pytest

from src.t08.lineage import (
    ancestors_of,
    build_index,
    descendants_of,
    held_ancestor,
    lineage_path,
    scope_for,
)
from src.t08.loader import load_inputs

FIXTURE_DIR = Path("fixtures/t08_deletion")


def test_load_inputs_valid():
    graph, requests = load_inputs(FIXTURE_DIR)
    assert len(graph) == 212
    assert len(requests) == 10

    # Every artefact must have required fields
    for aid, a in graph.items():
        assert a["artefact_id"] == aid
        assert a["type"]
        assert isinstance(a["subject_ids"], list) and len(a["subject_ids"]) > 0
        assert isinstance(a["parent_ids"], list)
        assert isinstance(a["acl"], list)
        assert a["legal_hold"] is None or isinstance(a["legal_hold"], str)
        assert isinstance(a["origin_known"], bool)

    # Every request must have required fields
    for r in requests:
        assert r["request_id"].startswith("DR-")
        assert r["subject_id"].startswith("subj_")
        assert isinstance(r["identity_verified"], bool)


def test_loader_rejects_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_inputs(tmp_path / "non_existent")


def test_loader_rejects_missing_file(tmp_path):
    (tmp_path / "data_graph.json").write_text(json.dumps({"artefacts": []}), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        load_inputs(tmp_path)


def test_loader_rejects_bad_json(tmp_path):
    (tmp_path / "data_graph.json").write_text("{ broken json ", encoding="utf-8")
    (tmp_path / "requests.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to parse JSON"):
        load_inputs(tmp_path)


def test_loader_rejects_missing_artefact_field(tmp_path):
    art = {
        "artefact_id": "a0001",
        "type": "raw_video",
        # missing subject_ids
        "parent_ids": [],
        "acl": ["data-platform"],
        "legal_hold": None,
        "origin_known": True,
    }
    (tmp_path / "data_graph.json").write_text(json.dumps({"artefacts": [art]}), encoding="utf-8")
    (tmp_path / "requests.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field: 'subject_ids'"):
        load_inputs(tmp_path)


def test_loader_rejects_empty_subject_ids(tmp_path):
    art = {
        "artefact_id": "a0001",
        "type": "raw_video",
        "subject_ids": [],
        "parent_ids": [],
        "acl": ["data-platform"],
        "legal_hold": None,
        "origin_known": True,
    }
    (tmp_path / "data_graph.json").write_text(json.dumps({"artefacts": [art]}), encoding="utf-8")
    (tmp_path / "requests.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="empty subject_ids"):
        load_inputs(tmp_path)


def test_loader_rejects_duplicate_artefact_id(tmp_path):
    art = {
        "artefact_id": "a0001",
        "type": "raw_video",
        "subject_ids": ["subj_00"],
        "parent_ids": [],
        "acl": ["data-platform"],
        "legal_hold": None,
        "origin_known": True,
    }
    (tmp_path / "data_graph.json").write_text(json.dumps({"artefacts": [art, art]}), encoding="utf-8")
    (tmp_path / "requests.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate artefact_id"):
        load_inputs(tmp_path)


def test_loader_rejects_duplicate_request_id(tmp_path):
    req = {
        "request_id": "DR-001",
        "subject_id": "subj_01",
        "received_at": "2026-11-01T09:00:00+07:00",
        "deadline": "2026-12-01T09:00:00+07:00",
        "channel": "app",
        "identity_verified": True,
    }
    (tmp_path / "data_graph.json").write_text(json.dumps({"artefacts": []}), encoding="utf-8")
    (tmp_path / "requests.json").write_text(json.dumps([req, req]), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate request_id"):
        load_inputs(tmp_path)


def test_scope_for_total_and_determinism():
    graph, requests = load_inputs(FIXTURE_DIR)
    total_pairs = 0
    for r in requests:
        scope = scope_for(graph, r["subject_id"])
        assert scope == sorted(scope), "Scope must be sorted"
        assert len(scope) == len(set(scope)), "Scope must not contain duplicates"
        total_pairs += len(scope)

    # PLAN_T08 §2.1: total pairs across all 10 requests is exactly 158
    assert total_pairs == 158


def test_scope_for_trap_b6():
    """Trap B6: Frame a0011 has subj_00 and subj_01, but its children a0012, a0013 only belong to subj_00."""
    graph, _ = load_inputs(FIXTURE_DIR)
    scope_subj_01 = scope_for(graph, "subj_01")
    assert "a0011" in scope_subj_01
    assert "a0012" not in scope_subj_01
    assert "a0013" not in scope_subj_01

    scope_subj_00 = scope_for(graph, "subj_00")
    assert "a0011" in scope_subj_00
    assert "a0012" in scope_subj_00
    assert "a0013" in scope_subj_00


def test_lineage_path():
    graph, _ = load_inputs(FIXTURE_DIR)
    # Root has single-element path
    assert lineage_path(graph, "a0043") == "a0043"
    assert lineage_path(graph, "a0001") == "a0001"

    # Multi-hop path from root to embedding
    assert lineage_path(graph, "a0047") == "a0043 > a0045 > a0046 > a0047"

    # Unknown artefact returns itself
    assert lineage_path(graph, "non_existent") == "non_existent"


def test_held_ancestor():
    graph, _ = load_inputs(FIXTURE_DIR)
    # a0043 is the root under legal hold LH-2026-03; held_ancestor should be None (it is self, not ancestor)
    assert held_ancestor(graph, "a0043") is None

    # Descendants of a0043 inherit LH-2026-03 as held_ancestor
    assert held_ancestor(graph, "a0044") == "LH-2026-03"
    assert held_ancestor(graph, "a0045") == "LH-2026-03"
    assert held_ancestor(graph, "a0046") == "LH-2026-03"
    assert held_ancestor(graph, "a0047") == "LH-2026-03"

    # Artefact without any held ancestors returns None
    assert held_ancestor(graph, "a0001") is None
    assert held_ancestor(graph, "a0002") is None


def test_build_index_clean_fixture():
    graph, _ = load_inputs(FIXTURE_DIR)
    index = build_index(graph)
    # Clean fixture must not have any warnings (dangling parents or cycles)
    assert index["warnings"] == []
    assert len(index["parents"]) == 212
    assert len(index["ancestors"]) == 212

    # Children relationship check
    assert "a0002" in index["children"]["a0001"]
    assert "a0003" in index["children"]["a0001"]


def test_build_index_dangling_parent():
    graph = {
        "a0001": {
            "artefact_id": "a0001",
            "type": "frame",
            "subject_ids": ["subj_01"],
            "parent_ids": ["non_existent_parent"],
            "acl": ["data-platform"],
            "legal_hold": None,
            "origin_known": True,
        }
    }
    index = build_index(graph)
    assert len(index["warnings"]) == 1
    w = index["warnings"][0]
    assert w["type"] == "dangling_parent"
    assert w["artefact_id"] == "a0001"
    assert w["parent_id"] == "non_existent_parent"


def test_build_index_cycle_detection():
    graph = {
        "node_a": {
            "artefact_id": "node_a",
            "type": "frame",
            "subject_ids": ["subj_01"],
            "parent_ids": ["node_b"],
            "acl": ["data-platform"],
            "legal_hold": None,
            "origin_known": True,
        },
        "node_b": {
            "artefact_id": "node_b",
            "type": "frame",
            "subject_ids": ["subj_01"],
            "parent_ids": ["node_a"],
            "acl": ["data-platform"],
            "legal_hold": None,
            "origin_known": True,
        },
    }
    index = build_index(graph)
    cycles = [w for w in index["warnings"] if w["type"] == "cycle"]
    assert len(cycles) > 0
    assert any("node_a" in c["cycle"] and "node_b" in c["cycle"] for c in cycles)


def test_helpers_ancestors_and_descendants():
    graph, _ = load_inputs(FIXTURE_DIR)
    anc = ancestors_of(graph, "a0047")
    assert anc == ["a0043", "a0045", "a0046"]

    desc = descendants_of(graph, "a0043")
    assert "a0044" in desc
    assert "a0045" in desc
    assert "a0046" in desc
    assert "a0047" in desc

