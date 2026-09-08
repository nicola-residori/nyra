from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]
UNIT = ROOT / "deploy/systemd/nyra-memory.service"
BOOTSTRAP = ROOT / "deploy/bootstrap/memory.sh"
VERIFY = ROOT / "deploy/verify/memory.sh"
BACKUP = ROOT / "deploy/backup/memory.sh"
RESTORE = ROOT / "deploy/restore/memory.sh"


def test_memory_deployment_scripts_have_valid_shell_syntax():
    for script in (BOOTSTRAP, VERIFY, BACKUP, RESTORE):
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_memory_unit_uses_locked_user_and_persistent_paths():
    source = UNIT.read_text()
    assert "User=nyra-memory" in source
    assert "Group=nyra-memory" in source
    assert "NYRA_MEMORY_DATA_ROOT=/var/lib/nyra-memory" in source
    assert "HF_HOME=/var/lib/nyra-memory/models/huggingface" in source
    assert "WorkingDirectory=/opt/nyra-memory" in source
    assert "NoNewPrivileges=true" in source


def test_bootstrap_installs_service_preloads_model_and_verifies():
    source = BOOTSTRAP.read_text()
    for required in (
        "useradd --system",
        'cp -a "$SOURCE_ROOT/memory/."',
        'cp -a "$SOURCE_ROOT/shared"',
        "SentenceTransformerEmbeddingProvider",
        "systemctl enable nyra-memory.service",
        "deploy/verify/memory.sh",
    ):
        assert required in source


def test_verifier_covers_service_storage_model_api_and_snapshot():
    source = VERIFY.read_text()
    for required in (
        'id "$SERVICE_USER"',
        "systemctl is-enabled",
        "systemctl is-active",
        "memory.sqlite3",
        "/health",
        "/ready",
        "embedding_model",
        "--snapshot",
        "--verify-snapshot",
    ):
        assert required in source


def test_backup_is_sqlite_consistent_and_hashed():
    source = BACKUP.read_text()
    assert ".backup" in source
    assert "sha256sum" in source
    assert "tar" in source


def test_restore_refuses_running_service_and_verifies_hash():
    source = RESTORE.read_text()
    assert "systemctl is-active --quiet nyra-memory" in source
    assert "sha256sum -c" in source
    assert "chown" in source
    assert "memory.sqlite3" in source

