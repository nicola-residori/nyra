from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parents[2]

def load_module(filename: str, name: str):
    path = ROOT / "speaker-id" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module



@dataclass(frozen=True)
class ConfigSnapshot:
    threshold: float
    margin: float
    revision: int


def test_diagnostic_persists_operation_snapshot_and_ranked_candidates(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_diagnostics_persist")
    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()

    snapshot = ConfigSnapshot(threshold=.41, margin=.08, revision=7)
    diagnostic_id = store.record(
        outcome="IDENTIFIED",
        identified_user_id="alice",
        best_score=.88,
        reason_code=None,
        candidate_scores={
            "charlie": .33,
            "alice": .88,
            "bob": .61,
        },
        preprocessing_version="prep-3",
        model_revision="ecapa-r12",
        config_snapshot=snapshot,
    )

    record = store.get(diagnostic_id)
    assert record is not None
    assert record.outcome == "IDENTIFIED"
    assert record.identified_user_id == "alice"
    assert record.best_score == .88
    assert record.preprocessing_version == "prep-3"
    assert record.model_revision == "ecapa-r12"
    assert record.config_revision == 7
    assert record.threshold == .41
    assert record.margin == .08

    candidates = store.list_candidates(diagnostic_id)
    assert [(row.user_id, row.score, row.rank) for row in candidates] == [
        ("alice", .88, 1),
        ("bob", .61, 2),
        ("charlie", .33, 3),
    ]


def test_diagnostic_candidate_rows_are_normalized(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_diagnostics_normalized")
    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()

    diagnostic_id = store.record(
        outcome="NOT_RECOGNIZED",
        identified_user_id=None,
        best_score=.55,
        reason_code="BELOW_THRESHOLD",
        candidate_scores={"a": .55, "b": .20},
        preprocessing_version="prep-1",
        model_revision="model-1",
        config_snapshot=ConfigSnapshot(threshold=.60, margin=.07, revision=11),
    )

    with store._connect() as connection:
        columns = [
            row["name"]
            for row in connection.execute("PRAGMA table_info(diagnostic_candidates)")
        ]
        rows = connection.execute(
            """
            SELECT diagnostic_id, user_id, score, rank
            FROM diagnostic_candidates
            WHERE diagnostic_id = ?
            ORDER BY rank
            """,
            (diagnostic_id,),
        ).fetchall()

    assert columns == ["diagnostic_id", "user_id", "score", "rank"]
    assert [(row["user_id"], row["rank"]) for row in rows] == [("a", 1), ("b", 2)]


def test_empty_candidate_set_is_persisted_without_fake_rows(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_diagnostics_empty")
    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()

    diagnostic_id = store.record(
        outcome="NOT_RECOGNIZED",
        identified_user_id=None,
        best_score=None,
        reason_code="NO_PROFILES",
        candidate_scores={},
        preprocessing_version="prep-1",
        model_revision="model-1",
        config_snapshot=ConfigSnapshot(threshold=.40, margin=.07, revision=2),
    )

    assert store.list_candidates(diagnostic_id) == []
    assert store.get(diagnostic_id).reason_code == "NO_PROFILES"


def test_diagnostics_list_supports_admin_filters_and_correlation(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_diagnostics_admin")
    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()
    diagnostic_id = store.record(
        outcome="IDENTIFIED", identified_user_id="alice", best_score=.88,
        reason_code=None, candidate_scores={"alice": .88},
        preprocessing_version="prep-1", model_revision="model-1",
        config_snapshot=ConfigSnapshot(threshold=.4, margin=.07, revision=1),
        source_id="nyra-mansarda", request_id="req_1", session_id="ses_1",
        trace_id="trc_1", span_id="SPEAKER_ID#identify#1",
    )

    rows = store.list(source_id="nyra-mansarda", outcome="IDENTIFIED", user_id="alice")
    assert [row.diagnostic_id for row in rows] == [diagnostic_id]
    assert rows[0].request_id == "req_1"
    assert rows[0].trace_id == "trc_1"
