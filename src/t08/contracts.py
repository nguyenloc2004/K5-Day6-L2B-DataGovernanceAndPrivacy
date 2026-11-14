"""Shared types and constants for T08. OWNER: M1.

Do NOT change a function signature in loader/lineage/policy/audit without telling the whole team:
pipeline.py and the tests depend on them.
"""
from __future__ import annotations

from typing import TypedDict

ACTIONS = ("delete", "retain_legal_hold", "escalate")

# Higher = shown earlier in the review queue (rank step). Tie-break: nearer deadline first.
REVIEW_PRIORITY = {
    "retain_legal_hold": 3.0,
    "escalate": 2.0,
    "delete_derived_from_held": 1.5,   # delete, but an ancestor is under legal hold (Q1 decision)
    "delete": 0.0,
}

# Columns produced by pipeline.process(). The first three are the graded contract.
SCORED_COLUMNS = [
    "request_id", "artefact_id", "action",
    "item_id",          # "<request_id>|<artefact_id>" — unique id used by the review queue
    "score",            # review priority, higher = review first
    "reason",           # reason_code of the rule that fired
    "rule_id",
    "type", "subject_ids", "lineage_path", "held_ancestor", "deadline",
]


class Artefact(TypedDict, total=False):
    artefact_id: str
    type: str
    subject_ids: list[str]
    parent_ids: list[str]
    uri: str
    owner: str
    acl: list[str]
    legal_hold: str | None
    origin_known: bool
    created_at: str
    filename: str


class Request(TypedDict, total=False):
    request_id: str
    subject_id: str
    received_at: str
    deadline: str
    channel: str
    identity_verified: bool


Graph = dict[str, Artefact]     # artefact_id -> artefact


class Decision(TypedDict):
    action: str        # one of ACTIONS
    reason_code: str
    rule_id: str
    score: float       # review priority (see REVIEW_PRIORITY)


def item_id(request_id: str, artefact_id: str) -> str:
    return f"{request_id}|{artefact_id}"


def split_item_id(iid: str) -> tuple[str, str]:
    request_id, artefact_id = iid.split("|", 1)
    return request_id, artefact_id
