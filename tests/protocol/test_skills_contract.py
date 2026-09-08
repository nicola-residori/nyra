from shared.protocol.skills import (
    JobStatus,
    SkillCheckRequest,
    SkillExecuteRequest,
    SkillOutcome,
)


def test_skill_outcomes_are_contract_exact():
    assert [x.value for x in SkillOutcome] == [
        "HANDLED",
        "MISS",
        "NEEDS_CLARIFICATION",
        "FAILED",
    ]


def test_job_running_and_unknown_outcome_are_distinct_states():
    assert JobStatus.RUNNING.value == "RUNNING"
    assert JobStatus.UNKNOWN_OUTCOME.value == "UNKNOWN_OUTCOME"


def test_skill_requests_forbid_unknown_fields():
    assert SkillCheckRequest.model_config["extra"] == "forbid"
    assert SkillExecuteRequest.model_config["extra"] == "forbid"
