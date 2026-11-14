"""Baseline (PLAN_T08 §2.4): delete only the raw video found by filename, no lineage. OWNER: M4.

Run:
    python -m src.main --track t08 --pipeline src.t08.baseline --output out/baseline --run-name baseline --offline --seed 42

TODO M4: for each request, find raw_video artefacts whose filename contains the subject_id,
write actions.csv (request_id, artefact_id, action=delete) + audit + decision.
"""
from __future__ import annotations


def run(ctx) -> None:
    raise NotImplementedError("T08 baseline not implemented yet (owner: M4)")
