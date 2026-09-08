from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_public_status_marks_m4_complete_and_deployed():
    roadmap = (ROOT / "ROADMAP.md").read_text()
    state = (ROOT / "docs/state/CURRENT_STATE.md").read_text()
    readme = (ROOT / "README.md").read_text()

    assert "Milestone 4 - Memory and context\n\n**Status: Complete and deployed in production**" in roadmap
    assert "Milestone 4 — Memory and Context — is complete and deployed in production." in state
    assert "Milestone 4 — Memory and context: complete and deployed in production." in readme


def test_memory_deployment_document_covers_recovery_and_router_boundary():
    source = (ROOT / "docs/deployment/MEMORY.md").read_text()
    for required in (
        "Debian 12",
        "nyra-memory",
        "Router",
        "backup",
        "restore",
        "rollback",
        "NYRA_MEMORY_URL",
        "/ready",
    ):
        assert required in source
