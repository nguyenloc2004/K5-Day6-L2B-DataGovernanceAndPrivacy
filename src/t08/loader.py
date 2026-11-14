"""Load data_graph.json + requests.json with schema validation. OWNER: M2.

Responsibilities:
  - Read data_graph.json and requests.json
  - Validate schema and required fields of every artefact and request
  - Reject duplicate artefact_id and request_id (fail loudly with clear ValueError)
  - Reject malformed JSON and missing files
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import Artefact, Graph, Request

REQUIRED_ARTEFACT_FIELDS: tuple[str, ...] = (
    "artefact_id",
    "type",
    "subject_ids",
    "parent_ids",
    "acl",
    "legal_hold",
    "origin_known",
)

REQUIRED_REQUEST_FIELDS: tuple[str, ...] = (
    "request_id",
    "subject_id",
    "received_at",
    "deadline",
    "channel",
    "identity_verified",
)


def _validate_artefact(raw: Any, index: int) -> Artefact:
    if not isinstance(raw, dict):
        raise ValueError(f"Artefact at index {index} must be a JSON object, got {type(raw).__name__}")

    for field in REQUIRED_ARTEFACT_FIELDS:
        if field not in raw:
            aid = raw.get("artefact_id", f"index_{index}")
            raise ValueError(f"Artefact {aid!r} is missing required field: {field!r}")

    aid = raw["artefact_id"]
    if not isinstance(aid, str) or not aid.strip():
        raise ValueError(f"Artefact at index {index} has invalid artefact_id: {aid!r} (must be non-empty string)")

    atype = raw["type"]
    if not isinstance(atype, str) or not atype.strip():
        raise ValueError(f"Artefact {aid!r} has invalid type: {atype!r} (must be non-empty string)")

    sids = raw["subject_ids"]
    if not isinstance(sids, list):
        raise ValueError(f"Artefact {aid!r} subject_ids must be a list, got {type(sids).__name__}")
    if len(sids) == 0:
        raise ValueError(f"Artefact {aid!r} has empty subject_ids: must be associated with at least 1 subject")
    for s in sids:
        if not isinstance(s, str) or not s.strip():
            raise ValueError(f"Artefact {aid!r} contains invalid subject_id: {s!r}")

    pids = raw["parent_ids"]
    if not isinstance(pids, list):
        raise ValueError(f"Artefact {aid!r} parent_ids must be a list, got {type(pids).__name__}")
    for p in pids:
        if not isinstance(p, str) or not p.strip():
            raise ValueError(f"Artefact {aid!r} contains invalid parent_id: {p!r}")

    acl = raw["acl"]
    if not isinstance(acl, list):
        raise ValueError(f"Artefact {aid!r} acl must be a list, got {type(acl).__name__}")
    for a_entry in acl:
        if not isinstance(a_entry, str) or not a_entry.strip():
            raise ValueError(f"Artefact {aid!r} contains invalid acl entry: {a_entry!r}")

    legal_hold = raw["legal_hold"]
    if legal_hold is not None and (not isinstance(legal_hold, str) or not legal_hold.strip()):
        raise ValueError(f"Artefact {aid!r} legal_hold must be None or non-empty string, got {legal_hold!r}")

    origin_known = raw["origin_known"]
    if not isinstance(origin_known, bool):
        raise ValueError(f"Artefact {aid!r} origin_known must be a boolean, got {origin_known!r}")

    return raw  # type: ignore[return-value]


def _validate_request(raw: Any, index: int) -> Request:
    if not isinstance(raw, dict):
        raise ValueError(f"Request at index {index} must be a JSON object, got {type(raw).__name__}")

    for field in REQUIRED_REQUEST_FIELDS:
        if field not in raw:
            rid = raw.get("request_id", f"index_{index}")
            raise ValueError(f"Request {rid!r} is missing required field: {field!r}")

    rid = raw["request_id"]
    if not isinstance(rid, str) or not rid.strip():
        raise ValueError(f"Request at index {index} has invalid request_id: {rid!r} (must be non-empty string)")

    sid = raw["subject_id"]
    if not isinstance(sid, str) or not sid.strip():
        raise ValueError(f"Request {rid!r} has invalid subject_id: {sid!r} (must be non-empty string)")

    for str_field in ("received_at", "deadline", "channel"):
        val = raw[str_field]
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"Request {rid!r} has invalid {str_field}: {val!r}")

    iv = raw["identity_verified"]
    if not isinstance(iv, bool):
        raise ValueError(f"Request {rid!r} identity_verified must be a boolean, got {iv!r}")

    return raw  # type: ignore[return-value]


def load_inputs(input_dir: str | Path) -> tuple[Graph, list[Request]]:
    """Load and validate data_graph.json and requests.json.

    Args:
        input_dir: Directory containing data_graph.json and requests.json.

    Returns:
        tuple[Graph, list[Request]]:
            - graph: mapping from artefact_id to validated Artefact dict.
            - requests: list of validated Request dicts.

    Raises:
        FileNotFoundError: If the input directory or files do not exist.
        ValueError: If JSON is invalid, required fields are missing, or IDs are duplicated.
    """
    d = Path(input_dir)
    if not d.exists() or not d.is_dir():
        raise FileNotFoundError(f"Input directory does not exist or is not a directory: {d}")

    graph_file = d / "data_graph.json"
    if not graph_file.is_file():
        raise FileNotFoundError(f"Missing required file: {graph_file}")

    requests_file = d / "requests.json"
    if not requests_file.is_file():
        raise FileNotFoundError(f"Missing required file: {requests_file}")

    try:
        raw_graph_data = json.loads(graph_file.read_text(encoding="utf-8"))
    except Exception as err:
        raise ValueError(f"Failed to parse JSON in {graph_file}: {err}") from err

    try:
        raw_requests_data = json.loads(requests_file.read_text(encoding="utf-8"))
    except Exception as err:
        raise ValueError(f"Failed to parse JSON in {requests_file}: {err}") from err

    if not isinstance(raw_graph_data, dict):
        raise ValueError(f"data_graph.json must be a JSON object, got {type(raw_graph_data).__name__}")

    raw_artefacts = raw_graph_data.get("artefacts")
    if not isinstance(raw_artefacts, list):
        raise ValueError("data_graph.json must contain an 'artefacts' list")

    graph: Graph = {}
    for idx, raw_art in enumerate(raw_artefacts):
        art = _validate_artefact(raw_art, idx)
        aid = art["artefact_id"]
        if aid in graph:
            raise ValueError(f"Duplicate artefact_id found in data_graph.json: {aid!r}")
        graph[aid] = art

    if not isinstance(raw_requests_data, list):
        raise ValueError(f"requests.json must be a JSON list, got {type(raw_requests_data).__name__}")

    requests: list[Request] = []
    seen_request_ids: set[str] = set()
    for idx, raw_req in enumerate(raw_requests_data):
        req = _validate_request(raw_req, idx)
        rid = req["request_id"]
        if rid in seen_request_ids:
            raise ValueError(f"Duplicate request_id found in requests.json: {rid!r}")
        seen_request_ids.add(rid)
        requests.append(req)

    return graph, requests
