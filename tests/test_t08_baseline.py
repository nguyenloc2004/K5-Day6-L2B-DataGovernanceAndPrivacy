"""Baseline tests (PLAN_T08 §2.4). OWNER: M4.

The baseline is the bar the PoC must beat, so these tests pin down both what it does and the
failures it is supposed to have (held videos deleted, derived data left behind).
"""
import json
from pathlib import Path

import pandas as pd

from src import main as runner

BASE = ["--config", "configs/lab.yaml", "--track", "t08", "--pipeline", "src.t08.baseline", "--offline", "--seed", "42"]
REAL = Path("fixtures/t08_deletion")


def _run(out, input_dir=None):
    args = BASE + ["--output", str(out)]
    if input_dir is not None:
        args += ["--input", str(input_dir)]
    return runner.main(args)


def _graph(input_dir):
    return {a["artefact_id"]: a for a in json.loads((Path(input_dir) / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]}


def _make_input(tmp_path, artefacts, requests):
    d = tmp_path / "in"
    d.mkdir(parents=True)
    (d / "data_graph.json").write_text(json.dumps({"artefacts": artefacts}), encoding="utf-8")
    (d / "requests.json").write_text(json.dumps(requests), encoding="utf-8")
    return d


def _raw(aid, subject, filename=None):
    a = {"artefact_id": aid, "type": "raw_video", "subject_ids": [subject], "parent_ids": []}
    if filename:
        a["filename"] = filename
    return a


def test_baseline_runs_and_writes_contract_files(tmp_path):
    assert _run(tmp_path) == 0
    actions = pd.read_csv(tmp_path / "actions.csv")
    assert list(actions.columns) == ["request_id", "artefact_id", "action"]
    assert set(actions.action) == {"delete"}
    assert not actions.duplicated(["request_id", "artefact_id"]).any()
    assert json.loads((tmp_path / "decision.json").read_text())["reason_code"] == "BASELINE_ONLY"


def test_baseline_deletes_raw_videos_only(tmp_path):
    """Failure mode 'only raw deleted': frames, crops, embeddings, backups and exports are left behind."""
    assert _run(tmp_path) == 0
    graph = _graph(REAL)
    actions = pd.read_csv(tmp_path / "actions.csv")
    assert {graph[a]["type"] for a in actions.artefact_id} == {"raw_video"}
    assert len(actions) == len(json.loads((REAL / "requests.json").read_text())), "one raw video per request on the lab fixture"


def test_baseline_deletes_videos_under_legal_hold(tmp_path):
    """The baseline's known bad number: it does not look at legal_hold, so it false-deletes held videos."""
    assert _run(tmp_path) == 0
    graph = _graph(REAL)
    actions = pd.read_csv(tmp_path / "actions.csv")
    held = [a for a in actions.artefact_id if graph[a]["legal_hold"]]
    assert held, "fixture has held raw videos; the baseline must (wrongly) delete them"


def test_baseline_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert _run(a) == 0 and _run(b) == 0
    assert (a / "actions.csv").read_bytes() == (b / "actions.csv").read_bytes()


def test_baseline_logs_one_audit_entry_per_row(tmp_path):
    assert _run(tmp_path) == 0
    logged = [json.loads(l)["item_id"] for l in (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert sorted(logged) == sorted(pd.read_csv(tmp_path / "actions.csv").artefact_id)


def test_baseline_filename_match_is_whole_token(tmp_path):
    """subj_1 must not match a file named for subj_10 (substring bug)."""
    d = _make_input(
        tmp_path,
        [_raw("x1", "subj_1", "drive_subj_1_000.mp4"), _raw("x10", "subj_10", "drive_subj_10_000.mp4")],
        [{"request_id": "R1", "subject_id": "subj_1"}],
    )
    out = tmp_path / "out"
    assert _run(out, d) == 0
    assert pd.read_csv(out / "actions.csv").artefact_id.tolist() == ["x1"]


def test_baseline_uses_filename_not_subject_ids_when_present(tmp_path):
    """Matching is by filename, as the track brief says; subject_ids is only a fallback."""
    d = _make_input(tmp_path, [_raw("x1", "other", "drive_subj_7_000.mp4")], [{"request_id": "R1", "subject_id": "subj_7"}])
    out = tmp_path / "out"
    assert _run(out, d) == 0
    assert pd.read_csv(out / "actions.csv").artefact_id.tolist() == ["x1"]


def test_baseline_falls_back_to_subject_ids_without_filename(tmp_path):
    """Graphs without filenames (like tests/data/t08_mini): one raw video per requester, held or not."""
    held = _raw("h1", "s_a")
    held["legal_hold"] = "LH-X"
    frame = {"artefact_id": "f1", "type": "frame", "subject_ids": ["s_a"], "parent_ids": ["h1"]}
    d = _make_input(tmp_path, [held, frame, _raw("v2", "s_b")],
                    [{"request_id": "R1", "subject_id": "s_a"}, {"request_id": "R2", "subject_id": "s_b"}])
    out = tmp_path / "out"
    assert _run(out, d) == 0
    actions = pd.read_csv(out / "actions.csv")
    assert set(zip(actions.request_id, actions.artefact_id)) == {("R1", "h1"), ("R2", "v2")}   # held video deleted, frame ignored


def test_baseline_with_no_match_writes_header_only_file(tmp_path):
    d = _make_input(tmp_path, [_raw("x1", "subj_1", "drive_subj_1_000.mp4")], [{"request_id": "R1", "subject_id": "subj_9"}])
    out = tmp_path / "out"
    assert _run(out, d) == 0
    actions = pd.read_csv(out / "actions.csv")
    assert list(actions.columns) == ["request_id", "artefact_id", "action"] and actions.empty


def test_baseline_bad_input_fails_loudly(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    (d / "data_graph.json").write_text("{not json", encoding="utf-8")
    (d / "requests.json").write_text("[]", encoding="utf-8")
    assert _run(tmp_path / "o1", d) == 2
    assert not (tmp_path / "o1" / "actions.csv").exists()

    d2 = _make_input(tmp_path / "x", [{"type": "raw_video"}], [])   # artefact without artefact_id
    assert _run(tmp_path / "o2", d2) == 2
