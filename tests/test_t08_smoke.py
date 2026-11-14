"""T08 smoke tests (M1 scaffold). Detailed tests: M4, see PLAN_T08 §5."""
import json

import pandas as pd

from src import main as runner

ARGS = ["--config", "configs/lab.yaml", "--track", "t08", "--offline", "--seed", "42"]


def _run(out):
    return runner.main(ARGS + ["--output", str(out)])


def test_t08_pipeline_runs_end_to_end(tmp_path):
    assert _run(tmp_path) == 0
    for f in ["actions.csv", "audit_log.jsonl", "review_queue.csv", "decision.json", "run_info.json"]:
        assert (tmp_path / f).exists(), f
    actions = pd.read_csv(tmp_path / "actions.csv")
    assert list(actions.columns[:3]) == ["request_id", "artefact_id", "action"]
    assert not actions.duplicated(["request_id", "artefact_id"]).any()
    assert set(actions.action) <= {"delete", "retain_legal_hold", "escalate"}
    assert json.loads((tmp_path / "decision.json").read_text())["owner"]


def test_t08_output_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert _run(a) == 0 and _run(b) == 0
    assert (a / "actions.csv").read_bytes() == (b / "actions.csv").read_bytes()


def test_t08_every_action_has_audit_entry(tmp_path):
    assert _run(tmp_path) == 0
    actions = pd.read_csv(tmp_path / "actions.csv")
    logged = {json.loads(l)["item_id"] for l in (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    assert set(actions.artefact_id) <= logged
