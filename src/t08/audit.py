"""Audit log, dry-run, review overrides. OWNER: M5.

Grader rule: an action counts as audited only if the audit entry has item_id == artefact_id.

STUB (M1 scaffold): one plain audit entry per action row; review overrides not applied yet.
TODO M5: richer entries (lineage_path, held_ancestor, deadline, "delete after hold expires"),
dry-run plan file, apply reviewer overrides (approve/reject/edit/escalate) with reviewer name.
"""
from __future__ import annotations

import pandas as pd


def write_audit(ctx, rows: pd.DataFrame) -> None:
    dry_run = bool(ctx.param("dry_run", True))
    for r in rows.itertuples(index=False):
        ctx.audit.log(actor="pipeline", action=f"plan:{r.action}" if dry_run else r.action,
                      item_id=r.artefact_id, after=r.action, reason=r.reason,
                      request_id=r.request_id, rule_id=r.rule_id, dry_run=dry_run)


def apply_review(ctx, scored: pd.DataFrame, reviewed: pd.DataFrame | None) -> pd.DataFrame:
    """Return scored with reviewer overrides applied. STUB: pass-through."""
    return scored
