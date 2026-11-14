"""Demo console (docs/PLAN_DEMO_T08.md): offline, complete, and never able to break the graded run."""
import json
import re

import pandas as pd

from src import main as runner
from src.t08 import dashboard

ARGS = ["--config", "configs/lab.yaml", "--track", "t08", "--offline", "--seed", "42"]


def _run(out):
    return runner.main(ARGS + ["--output", str(out)])


def _payload(out):
    page = (out / "dashboard.html").read_text(encoding="utf-8")
    m = re.search(r'<script id="dsr-data" type="application/json">(.*?)</script>', page, re.S)
    assert m, "embedded data block missing"
    return page, json.loads(m.group(1))


def test_dashboard_and_contact_sheet_are_generated_offline(tmp_path):
    assert _run(tmp_path) == 0
    assert (tmp_path / "contact_sheet.html").exists()
    page, data = _payload(tmp_path)
    assert "http://" not in page and "https://" not in page          # no CDN / external resources
    requests = json.loads(open("fixtures/t08_deletion/requests.json", encoding="utf-8").read())
    assert {q["request_id"] for q in data["requests"]} == {r["request_id"] for r in requests}
    actions = pd.read_csv(tmp_path / "actions.csv")
    assert len(data["rows"]) == len(actions)
    assert data["decision"]["owner"]


def test_tree_marks_other_peoples_data_out_of_scope(tmp_path):
    assert _run(tmp_path) == 0
    _, data = _payload(tmp_path)
    graph = {a["artefact_id"]: a for a in json.loads(open("fixtures/t08_deletion/data_graph.json", encoding="utf-8").read())["artefacts"]}
    subject = {q["request_id"]: q["subject_id"] for q in data["requests"]}
    n_oos = 0
    for rid, tree in data["trees"].items():
        ids = {n["id"] for n in tree["nodes"]}
        for n in tree["nodes"]:
            in_subject = subject[rid] in graph[n["id"]]["subject_ids"]
            assert (n["status"] in ("context", "out_of_scope")) == (not in_subject)
            n_oos += n["status"] == "out_of_scope"
        assert all(p in ids and c in ids for p, c in tree["edges"])
    assert n_oos > 0                                                 # trap B6 is visible somewhere


def test_review_loop_reduces_pending_and_records_reviewer(tmp_path):
    assert _run(tmp_path) == 0
    before = json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))
    _, data = _payload(tmp_path)
    pending_before = sum(q["pending"] for q in data["requests"])
    q = pd.read_csv(tmp_path / "review_queue.csv", dtype=str).fillna("")
    esc_rows = q[q.suggested_action == "escalate"].index[:2]
    q.loc[esc_rows, "reviewer"] = "Demo Reviewer"
    q.loc[esc_rows, "reviewer_decision"] = "approve"
    q.to_csv(tmp_path / "review_queue_reviewed.csv", index=False)

    assert _run(tmp_path) == 0
    _, data = _payload(tmp_path)
    assert sum(q["pending"] for q in data["requests"]) == pending_before - 2
    assert any(e["actor"] == "Demo Reviewer" for e in data["audit"])
    assert before["status"] == "HOLD"


def test_dashboard_failure_does_not_break_the_run(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("template broken")
    monkeypatch.setattr(dashboard, "render_dashboard", boom)
    assert _run(tmp_path) == 0
    assert (tmp_path / "actions.csv").exists()
    log = (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8")
    assert "dashboard_failed" in log
