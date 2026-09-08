from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]
VERIFY = ROOT / "deploy" / "verify" / "speaker-id.sh"
BOOTSTRAP = ROOT / "deploy" / "bootstrap" / "speaker-id.sh"


def test_speaker_id_verifier_has_valid_shell_syntax():
    subprocess.run(["bash", "-n", str(VERIFY)], check=True)


def test_speaker_id_verifier_covers_fresh_ct_and_reboot_contract():
    source = VERIFY.read_text()

    for required in (
        "id \"$SERVICE_USER\"",
        "systemctl is-enabled",
        "systemctl is-active",
        '"$APP_DIR/.venv/bin/python"',
        "speaker-id.sqlite3",
        "/health",
        "/ready",
        "SpeechBrainECAPAEngine",
        "--snapshot",
        "--verify-snapshot",
    ):
        assert required in source


def test_bootstrap_finishes_with_the_shared_deployment_verifier():
    assert 'deploy/verify/speaker-id.sh' in BOOTSTRAP.read_text()
