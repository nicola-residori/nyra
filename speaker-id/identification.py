from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


class IdentificationOutcome(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    NOT_RECOGNIZED = "NOT_RECOGNIZED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class IdentificationResult:
    outcome: IdentificationOutcome
    identified_user_id: str | None
    best_score: float | None
    diagnostic_id: str | None
    reason_code: str | None


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions must match")
    if not left:
        raise ValueError("embeddings must not be empty")

    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("embeddings must have non-zero magnitude")

    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def cosine_scores(
    *,
    query_embedding: Sequence[float],
    profile_centroids: Mapping[str, Sequence[float]],
) -> dict[str, float]:
    return {
        user_id: cosine_similarity(query_embedding, centroid)
        for user_id, centroid in profile_centroids.items()
    }


def classify_scores(
    scores: Mapping[str, float],
    *,
    threshold: float,
    margin: float,
    diagnostic_id: str | None = None,
) -> IdentificationResult:
    if not scores:
        return IdentificationResult(
            outcome=IdentificationOutcome.NOT_RECOGNIZED,
            identified_user_id=None,
            best_score=None,
            diagnostic_id=diagnostic_id,
            reason_code="NO_PROFILES",
        )

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best_user_id, best_score = ranked[0]

    if best_score < threshold:
        return IdentificationResult(
            outcome=IdentificationOutcome.NOT_RECOGNIZED,
            identified_user_id=None,
            best_score=best_score,
            diagnostic_id=diagnostic_id,
            reason_code="BELOW_THRESHOLD",
        )

    if len(ranked) > 1:
        second_score = ranked[1][1]
        if best_score - second_score < margin:
            return IdentificationResult(
                outcome=IdentificationOutcome.NOT_RECOGNIZED,
                identified_user_id=None,
                best_score=best_score,
                diagnostic_id=diagnostic_id,
                reason_code="AMBIGUOUS_MARGIN",
            )

    return IdentificationResult(
        outcome=IdentificationOutcome.IDENTIFIED,
        identified_user_id=best_user_id,
        best_score=best_score,
        diagnostic_id=diagnostic_id,
        reason_code=None,
    )


def identify_embedding(
    *,
    query_embedding: Sequence[float],
    profile_centroids: Mapping[str, Sequence[float]],
    threshold: float,
    margin: float,
    diagnostic_id: str | None = None,
) -> IdentificationResult:
    scores = cosine_scores(
        query_embedding=query_embedding,
        profile_centroids=profile_centroids,
    )
    return classify_scores(
        scores,
        threshold=threshold,
        margin=margin,
        diagnostic_id=diagnostic_id,
    )


def failed_result(
    *,
    diagnostic_id: str | None,
    reason_code: str,
) -> IdentificationResult:
    return IdentificationResult(
        outcome=IdentificationOutcome.FAILED,
        identified_user_id=None,
        best_score=None,
        diagnostic_id=diagnostic_id,
        reason_code=reason_code,
    )
