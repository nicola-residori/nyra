from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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



@pytest.mark.parametrize(
    ("scores", "threshold", "margin", "expected"),
    [
        ({"a": .82, "b": .50}, .40, .07, "IDENTIFIED"),
        ({"a": .82, "b": .79}, .40, .07, "NOT_RECOGNIZED"),
        ({"a": .35, "b": .20}, .40, .07, "NOT_RECOGNIZED"),
        ({}, .40, .07, "NOT_RECOGNIZED"),
    ],
)
def test_classification(scores, threshold, margin, expected):
    identification = load_module("identification.py", f"nyra_identification_{expected}_{len(scores)}")
    result = identification.classify_scores(
        scores,
        threshold=threshold,
        margin=margin,
    )
    assert result.outcome.value == expected


def test_identified_result_contains_only_best_user_and_score():
    identification = load_module("identification.py", "nyra_identification_best")
    result = identification.classify_scores(
        {"alice": .81, "bob": .52, "charlie": .11},
        threshold=.40,
        margin=.07,
        diagnostic_id="diag-1",
    )

    assert result.outcome.value == "IDENTIFIED"
    assert result.identified_user_id == "alice"
    assert result.best_score == pytest.approx(.81)
    assert result.diagnostic_id == "diag-1"
    assert result.reason_code is None
    assert not hasattr(result, "candidate_scores")


def test_not_recognized_result_does_not_expose_candidate_identity():
    identification = load_module("identification.py", "nyra_identification_ambiguous")
    result = identification.classify_scores(
        {"alice": .81, "bob": .78},
        threshold=.40,
        margin=.07,
        diagnostic_id="diag-2",
    )

    assert result.outcome.value == "NOT_RECOGNIZED"
    assert result.identified_user_id is None
    assert result.best_score == pytest.approx(.81)
    assert result.reason_code == "AMBIGUOUS_MARGIN"


def test_cosine_scores_all_profiles_without_source_filter():
    identification = load_module("identification.py", "nyra_identification_cosine")
    profiles = {
        "alice": [1.0, 0.0],
        "bob": [0.0, 1.0],
        "charlie": [1.0, 1.0],
    }

    scores = identification.cosine_scores(
        query_embedding=[1.0, 0.0],
        profile_centroids=profiles,
    )

    assert set(scores) == {"alice", "bob", "charlie"}
    assert scores["alice"] == pytest.approx(1.0)
    assert scores["bob"] == pytest.approx(0.0)
    assert scores["charlie"] == pytest.approx(2 ** -0.5)


def test_identify_embedding_uses_all_profile_centroids():
    identification = load_module("identification.py", "nyra_identification_pipeline")
    result = identification.identify_embedding(
        query_embedding=[0.0, 1.0],
        profile_centroids={
            "wrong-source-user": [1.0, 0.0],
            "correct-user": [0.0, 1.0],
        },
        threshold=.40,
        margin=.07,
        diagnostic_id="diag-all",
    )

    assert result.outcome.value == "IDENTIFIED"
    assert result.identified_user_id == "correct-user"


def test_failed_result_is_distinct_from_not_recognized():
    identification = load_module("identification.py", "nyra_identification_failed")
    result = identification.failed_result(
        diagnostic_id="diag-f",
        reason_code="MODEL_ERROR",
    )

    assert result.outcome.value == "FAILED"
    assert result.identified_user_id is None
    assert result.best_score is None
    assert result.diagnostic_id == "diag-f"
    assert result.reason_code == "MODEL_ERROR"
