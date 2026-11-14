"""Load data_graph.json + requests.json. OWNER: M2.

STUB (M1 scaffold): reads the files with no validation.
TODO M2:
  - validate required fields of every artefact / request -> raise ValueError with a clear message
  - reject duplicate artefact_id / request_id
  - log data warnings (dangling parent_ids, unknown types) instead of silently ignoring them
"""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import Graph, Request


def load_inputs(input_dir: str | Path) -> tuple[Graph, list[Request]]:
    d = Path(input_dir)
    raw = json.loads((d / "data_graph.json").read_text(encoding="utf-8"))
    graph: Graph = {a["artefact_id"]: a for a in raw["artefacts"]}
    requests: list[Request] = json.loads((d / "requests.json").read_text(encoding="utf-8"))
    return graph, requests
