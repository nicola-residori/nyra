from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_systemd_unit_starts_skills_app_with_persistent_job_db():
    unit = read("deploy/systemd/nyra-skills.service")

    assert "ExecStart=/opt/nyra-skills/.venv/bin/uvicorn skills.app:app" in unit
    assert "WorkingDirectory=/opt/nyra-skills" in unit
    assert "EnvironmentFile=-/etc/nyra/skills.env" in unit
    assert "NYRA_SKILLS_JOB_DB_PATH=/var/lib/nyra-skills/jobs.sqlite3" in unit
    assert "ReadWritePaths=/var/lib/nyra-skills" in unit
    assert "User=root" in unit


def test_bootstrap_is_repeatable_and_preserves_data_and_operator_config():
    script = read("deploy/bootstrap/skills.sh")

    assert "set -euo pipefail" in script
    assert 'DATA_DIR=${DATA_DIR:-/var/lib/nyra-skills}' in script
    assert 'CONFIG_FILE=${CONFIG_FILE:-$CONFIG_DIR/skills.env}' in script
    assert 'rm -rf "$APP_DIR/skills" "$APP_DIR/shared"' in script
    assert 'rm -rf "$DATA_DIR"' not in script
    assert 'if [[ ! -f $CONFIG_FILE ]]; then' in script
    assert 'cp -a "$SOURCE_ROOT/skills" "$APP_DIR/skills"' in script
    assert 'cp -a "$SOURCE_ROOT/shared" "$APP_DIR/shared"' in script
    assert "systemctl enable" in script
    assert "systemctl restart" in script
    assert "deploy/verify/skills.sh" in script


def test_backup_includes_jobs_database_config_and_checksums():
    script = read("deploy/backup/skills.sh")

    assert "set -euo pipefail" in script
    assert 'DATABASE=${DATABASE:-$DATA_DIR/jobs.sqlite3}' in script
    assert 'CONFIG_FILE=${CONFIG_FILE:-/etc/nyra/skills.env}' in script
    assert "sqlite3" in script
    assert ".backup" in script
    assert "config/skills.env" in script
    assert "SHA256SUMS" in script
    assert "sha256sum" in script


def test_restore_requires_explicit_targets_and_refuses_unsafe_overwrite():
    script = read("deploy/restore/skills.sh")

    assert "set -euo pipefail" in script
    assert "--data-dir" in script
    assert "--config-file" in script
    assert "--force" in script
    assert "restore target already exists" in script
    assert "systemctl is-active" in script
    assert "unexpected archive member" in script
    assert "sha256sum -c SHA256SUMS" in script
    assert "PRAGMA integrity_check" in script


def test_verifier_checks_health_ready_systemd_and_writable_store():
    script = read("deploy/verify/skills.sh")

    assert "set -euo pipefail" in script
    assert "systemctl is-enabled" in script
    assert "systemctl is-active" in script
    assert '"$BASE_URL/health"' in script
    assert '"$BASE_URL/ready"' in script
    assert 'test -w "$DATA_DIR"' in script
    assert ".write-test-$$" in script
    assert "PRAGMA integrity_check" in script


def test_all_skills_shell_assets_use_strict_shell_mode():
    paths = [
        "deploy/bootstrap/skills.sh",
        "deploy/verify/skills.sh",
        "deploy/backup/skills.sh",
        "deploy/restore/skills.sh",
    ]
    for path in paths:
        assert "set -euo pipefail" in read(path), path


def test_skills_deployment_guide_documents_persistence_backup_restore_and_gate():
    guide = read("docs/deployment/SKILLS.md")

    assert "/opt/nyra-skills" in guide
    assert "/var/lib/nyra-skills/jobs.sqlite3" in guide
    assert "/etc/nyra/skills.env" in guide
    assert "deploy/backup/skills.sh" in guide
    assert "deploy/restore/skills.sh" in guide
    assert "--force" in guide
    assert "explicit" in guide.casefold()
    assert "Task 19" in guide
