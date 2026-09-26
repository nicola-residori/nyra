from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p): return (ROOT/p).read_text()
def test_llm_deployment_assets_exist_and_are_strict():
    paths=["deploy/systemd/nyra-llm.service","deploy/bootstrap/llm.sh","deploy/backup/llm.sh","deploy/restore/llm.sh","deploy/verify/llm.sh","docs/deployment/LLM.md"]
    for p in paths: assert (ROOT/p).exists(),p
    for p in paths[1:5]: assert "set -euo pipefail" in read(p)
def test_llm_unit_and_bootstrap_are_secret_free_defaults():
    unit=read("deploy/systemd/nyra-llm.service"); boot=read("deploy/bootstrap/llm.sh")
    assert "llm.app:app" in unit
    assert "/etc/nyra/llm.env" in unit
    assert "OPENAI_API_KEY=" not in boot and "ANTHROPIC_API_KEY=" not in boot
def test_llm_guide_documents_backup_restore_and_no_paid_readiness():
    guide=read("docs/deployment/LLM.md")
    assert "deploy/backup/llm.sh" in guide and "deploy/restore/llm.sh" in guide
    assert "readiness" in guide.casefold() and "inference" in guide.casefold()
