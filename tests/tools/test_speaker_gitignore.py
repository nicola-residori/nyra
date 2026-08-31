from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _check_ignore(path: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["git", "check-ignore", "-v", path],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    return result.returncode == 0, result.stdout


def test_real_speaker_entrypoint_is_ignored():
    ignored, detail = _check_ignore("esphome/nyra-mansarda.yaml")
    assert ignored, detail


def test_real_speaker_device_definition_is_ignored():
    ignored, detail = _check_ignore("esphome/devices/nyra-mansarda.yaml")
    assert ignored, detail


def test_real_speaker_secret_is_ignored():
    ignored, detail = _check_ignore("esphome/device_secrets/nyra-mansarda.yaml")
    assert ignored, detail


def test_public_speaker_example_is_not_ignored():
    ignored, detail = _check_ignore("esphome/devices/nyra-speaker.example.yaml")
    assert not ignored, detail


def test_private_secrets_readme_is_not_ignored():
    ignored, detail = _check_ignore("esphome/device_secrets/README.md")
    assert not ignored, detail
