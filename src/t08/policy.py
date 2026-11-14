"""Configured T08 deletion policy. OWNER: M3.

Rules are evaluated top-to-bottom. ``hold_scope: direct`` is the group's
experiment assumption, not a legal conclusion. No fixture IDs are hard-coded.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .contracts import ACTIONS, Decision, Artefact, Request

_DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "configs" / "t08_policy.yaml"
_EXPECTED_RULES = tuple(f"R{i}" for i in range(1, 8))
_ALLOWED_HOLD_SCOPES = {"direct", "descendants"}
_REQUIRED_SCORE_KEYS = {"retain_legal_hold", "escalate", "delete_derived_from_held", "delete"}


@lru_cache(maxsize=16)
def _load_policy(path_string: str) -> dict[str, Any]:
    """Load and validate a policy file; cache by resolved path."""
    path = Path(path_string).expanduser().resolve()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read T08 policy file {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise ValueError(f"invalid T08 policy file {path}: expected a mapping with rules")

    rules = data["rules"]
    actual_ids = tuple(rule.get("id") for rule in rules if isinstance(rule, dict))
    if len(actual_ids) != len(rules) or actual_ids != _EXPECTED_RULES:
        raise ValueError(f"invalid T08 policy rule order in {path}: expected {_EXPECTED_RULES}, got {actual_ids}")
    for rule in rules:
        if rule.get("action") not in ACTIONS:
            raise ValueError(f"invalid action in T08 policy rule {rule['id']}: {rule.get('action')!r}")
        if not rule.get("reason_code") or not rule.get("source"):
            raise ValueError(f"T08 policy rule {rule['id']} must include reason_code and source")

    scores = data.get("review_scores")
    if not isinstance(scores, dict) or set(scores) != _REQUIRED_SCORE_KEYS:
        raise ValueError(f"T08 policy file {path} must define review_scores {sorted(_REQUIRED_SCORE_KEYS)}")
    try:
        scores = {key: float(value) for key, value in scores.items()}
    except (TypeError, ValueError) as exc:
        raise ValueError("T08 review scores must be numeric") from exc
    if not (scores["retain_legal_hold"] > scores["delete_derived_from_held"] > scores["escalate"] > scores["delete"]):
        raise ValueError("T08 review scores must order hold > held-derived > escalate > delete")
    data["review_scores"] = scores
    return data


def _decision(policy: dict[str, Any], rule_id: str, score_key: str, action: str | None = None) -> Decision:
    rule = next(rule for rule in policy["rules"] if rule["id"] == rule_id)
    selected_action = action or rule["action"]
    if selected_action not in ACTIONS:
        raise ValueError(f"invalid configured action {selected_action!r} for policy rule {rule_id}")
    return Decision(action=selected_action, reason_code=rule["reason_code"], rule_id=rule_id,
                    score=policy["review_scores"][score_key])


def _has_active_hold(artefact: Artefact) -> bool:
    """A non-empty hold identifier marks a direct hold; mapping forms are accepted."""
    value = artefact.get("legal_hold")
    if isinstance(value, dict):
        value = value.get("id") or value.get("hold_id")
    return value is not None and value is not False and str(value).strip() != ""


def decide_action(artefact: Artefact, request: Request, info: dict, params: dict) -> Decision:
    """Return action, reason, rule and review score for one in-scope pair.

    ``info`` is provided by lineage.py (``held_ancestor`` and ``lineage_path``).
    Missing identity/ACL/provenance signals fail closed to review rather than
    authorizing a deletion.
    """
    policy_path = Path(params.get("policy_file") or _DEFAULT_POLICY_PATH)
    policy = _load_policy(str(policy_path.expanduser().resolve()))
    hold_scope = str(params.get("hold_scope", policy.get("hold_scope_default", "direct")))
    if hold_scope not in _ALLOWED_HOLD_SCOPES:
        raise ValueError(f"invalid hold_scope {hold_scope!r}; expected one of {sorted(_ALLOWED_HOLD_SCOPES)}")

    # R1: an explicit hold marker takes precedence over all other conditions.
    if _has_active_hold(artefact):
        return _decision(policy, "R1", "retain_legal_hold")

    # R2: missing or non-true verification is not treated as verified.
    if request.get("identity_verified") is not True:
        return _decision(policy, "R2", "escalate")

    # R3: missing/malformed ACL or missing operator grant means no permission.
    operator_acl = str(params.get("operator_acl", "data-platform"))
    acl = artefact.get("acl")
    if not isinstance(acl, (list, tuple, set)) or operator_acl not in acl:
        return _decision(policy, "R3", "escalate")

    # R4: missing provenance is treated as unknown.
    if artefact.get("origin_known") is not True:
        return _decision(policy, "R4", "escalate")

    # R5: never automatically delete an artefact shared across subjects.
    subject_ids = artefact.get("subject_ids")
    if not isinstance(subject_ids, (list, tuple, set)) or not subject_ids or len(subject_ids) > 1:
        return _decision(policy, "R5", "escalate")

    # R6: descendants is an explicit ablation; direct scope is the team default.
    held_ancestor = info.get("held_ancestor")
    if held_ancestor and hold_scope == "descendants":
        return _decision(policy, "R6", "retain_legal_hold")
    if held_ancestor:
        # Direct scope deletes the derivative but elevates it in the review queue.
        return _decision(policy, "R6", "delete_derived_from_held", action="delete")

    # R7: only a verified, permitted, known-origin, subject-only artefact reaches delete.
    return _decision(policy, "R7", "delete")
