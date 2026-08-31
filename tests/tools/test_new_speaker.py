from pathlib import Path
import importlib.util
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "new-speaker.py"
PACKAGE = ROOT / "esphome" / "packages" / "nyra-speaker.yaml"
EXAMPLE = ROOT / "esphome" / "devices" / "nyra-speaker.example.yaml"
GITIGNORE = ROOT / "esphome" / ".gitignore"


def load_module():
    spec = importlib.util.spec_from_file_location("new_speaker", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generator_creates_parameterized_device_without_named_secret_keys(tmp_path):
    module = load_module()
    output = tmp_path / "devices" / "nyra-mansarda.yaml"
    result = module.create_device("nyra-mansarda", "Nyra Mansarda", output)
    text = output.read_text()

    assert result == output
    assert "device_name: nyra-mansarda" in text
    assert 'friendly_name: "Nyra Mansarda"' in text
    assert "source_id: nyra-mansarda" in text
    assert "!include ../packages/nyra-speaker.yaml" in text
    assert "${api_encryption_key}" in text
    assert "${ota_password}" in text
    assert "nyra_mansarda_api_key" not in text
    assert "nyra_mansarda_ota_password" not in text
    assert "192.168." not in text


def test_generator_creates_private_secret_file_and_wrapper_in_repo_layout(tmp_path):
    module = load_module()
    device_dir = tmp_path / "esphome" / "devices"
    output = device_dir / "nyra-mansarda.yaml"

    module.create_device("nyra-mansarda", "Nyra Mansarda", output)

    private_file = tmp_path / "esphome" / "device_secrets" / "nyra-mansarda.yaml"
    wrapper = tmp_path / "esphome" / "nyra-mansarda.yaml"

    assert private_file.exists()
    private_text = private_file.read_text()
    assert "api_encryption_key:" in private_text
    assert "ota_password:" in private_text
    assert "nyra_mansarda_api_key" not in private_text
    assert "nyra_mansarda_ota_password" not in private_text

    wrapper_text = wrapper.read_text()
    assert "substitutions: !include device_secrets/nyra-mansarda.yaml" in wrapper_text
    assert "!include devices/nyra-mansarda.yaml" in wrapper_text


def test_private_secret_values_are_random_between_devices(tmp_path):
    module = load_module()
    first = tmp_path / "a" / "esphome" / "devices" / "nyra-one.yaml"
    second = tmp_path / "b" / "esphome" / "devices" / "nyra-two.yaml"
    module.create_device("nyra-one", "Nyra One", first)
    module.create_device("nyra-two", "Nyra Two", second)
    first_secret = (tmp_path / "a" / "esphome" / "device_secrets" / "nyra-one.yaml").read_text()
    second_secret = (tmp_path / "b" / "esphome" / "device_secrets" / "nyra-two.yaml").read_text()
    assert first_secret != second_secret


def test_generator_rejects_invalid_slug(tmp_path):
    module = load_module()
    try:
        module.create_device("Nyra Mansarda", "Nyra Mansarda", tmp_path / "bad.yaml")
    except ValueError as exc:
        assert "lowercase" in str(exc)
    else:
        raise AssertionError("invalid slug was accepted")


def test_generator_refuses_to_overwrite_device_or_private_secret(tmp_path):
    module = load_module()
    output = tmp_path / "esphome" / "devices" / "nyra-mansarda.yaml"
    output.parent.mkdir(parents=True)
    output.write_text("existing")
    try:
        module.create_device("nyra-mansarda", "Nyra Mansarda", output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing device config was overwritten")


def test_common_package_exposes_adapter_effect_contract():
    text = PACKAGE.read_text()
    expected = {
        "nyra_listening_white_fast",
        "nyra_identifying_warm_white_comet",
        "nyra_identity_green_2blink",
        "nyra_identity_red_2blink",
        "nyra_identity_blue_2blink",
        "nyra_processing_local_turquoise_comet",
        "nyra_processing_global_rainbow_comet",
        "nyra_using_tool_yellow_comet",
        "nyra_speaking_purple_audio",
        "nyra_error_red",
    }
    for effect in expected:
        assert f'name: "{effect}"' in text

    assert 'name: "Nyra Close Feedback"' in text
    assert "id: nyra_close_feedback" in text


def test_repo_templates_contain_no_installation_specific_secrets_or_ips():
    texts = [PACKAGE.read_text(), EXAMPLE.read_text()]
    combined = "\n".join(texts)
    assert not re.search(r"192\\.168\\.\\d+\\.\\d+", combined)
    assert "TM3nBsrnJrDCnIid" not in combined
    assert "nyra-soggiorno" not in combined
    assert "nyra_mansarda_api_key" not in combined
    assert "nyra_room_api_key" not in combined


def test_common_package_contains_no_legacy_pipeline_or_room_logic():
    text = PACKAGE.read_text()
    assert "nyra_pipeline_stage" not in text
    assert "nyra_audio_capture" not in text
    assert "agent_wait" not in text
    assert "skill_wait" not in text


def test_device_secret_directory_is_gitignored():
    text = GITIGNORE.read_text()
    assert "device_secrets/*.yaml" in text


def test_cli_creates_device_wrapper_and_private_secret_by_default(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "nyra-mansarda", "Nyra Mansarda"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "esphome/devices/nyra-mansarda.yaml").exists()
    assert (tmp_path / "esphome/nyra-mansarda.yaml").exists()
    assert (tmp_path / "esphome/device_secrets/nyra-mansarda.yaml").exists()
    assert "Created private device secrets" in result.stdout


def test_common_package_does_not_override_upstream_wifi_hidden_option():
    text = PACKAGE.read_text()

    assert "hidden: ${hidden_ssid}" not in text


def test_common_package_uses_upstream_default_wake_words():
    text = PACKAGE.read_text()

    assert "micro_wake_word:" not in text
    assert "wakeword_model" not in text
    assert "nira_model" not in text


def test_generated_device_does_not_configure_custom_wake_word_or_hidden_ssid(tmp_path):
    module = load_module()
    output = tmp_path / "esphome" / "devices" / "nyra-mansarda.yaml"

    module.create_device("nyra-mansarda", "Nyra Mansarda", output)

    text = output.read_text()

    assert "hidden_ssid" not in text
    assert "wakeword_model" not in text
    assert "nira.json" not in text
