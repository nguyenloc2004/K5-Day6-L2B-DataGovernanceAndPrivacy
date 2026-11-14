"""Deletion policy: first matching rule wins. OWNER: M3.

Rule order (configs/t08_policy.yaml, PLAN_T08 §4.3):
  R1 legal hold -> R2 identity unverified -> R3 no permission -> R4 unknown origin
  -> R5 multi-subject -> R6 held ancestor (only if hold_scope=descendants) -> R7 delete

STUB (M1 scaffold): returns `escalate` for everything — safe (never a false delete) but scores 0
on completeness. TODO M3: implement R1..R7 reading the YAML, with no hard-coded artefact ids.
"""
from __future__ import annotations

from .contracts import REVIEW_PRIORITY, Artefact, Decision, Request


def decide_action(artefact: Artefact, request: Request, info: dict, params: dict) -> Decision:
    """Decide one (request, artefact) pair.

    info:   {"held_ancestor": str | None, "lineage_path": str}
    params: ctx.config["params"] (hold_scope, operator_acl, policy_file, ...)
    """
    return Decision(action="escalate", reason_code="STUB_NOT_IMPLEMENTED", rule_id="STUB",
                    score=REVIEW_PRIORITY["escalate"])
