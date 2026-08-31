from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "esphome" / "packages" / "nyra-speaker.yaml"


def test_common_package_exposes_read_only_diagnostic_source_id():
    text = PACKAGE.read_text()

    assert "text_sensor:" in text
    assert 'name: "Nyra Source ID"' in text
    assert "id: nyra_source_id" in text
    assert "entity_category: diagnostic" in text
    assert "text:" not in text


def test_common_package_publishes_source_id_at_boot():
    text = PACKAGE.read_text()

    assert "on_boot:" in text
    assert "text_sensor.template.publish:" in text
    assert "id: nyra_source_id" in text
    assert 'state: "${source_id}"' in text
