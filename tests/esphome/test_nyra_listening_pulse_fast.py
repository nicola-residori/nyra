from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "esphome/packages/nyra-speaker.yaml"
HA_OUTPUT = ROOT / "homeassistant/custom_components/nyra/esphome.py"


def test_local_listening_uses_white_pulse_fast():
    text = PACKAGE.read_text(encoding="utf-8")
    start = text.index("on_listening:")
    block = text[start:start + 1200]

    assert 'effect: "Pulse Fast"' in block or "effect: Pulse Fast" in block
    assert "red: 100%" in block
    assert "green: 100%" in block
    assert "blue: 100%" in block


def test_ha_listening_dispatch_uses_pulse_fast():
    text = HA_OUTPUT.read_text(encoding="utf-8")
    assert "Pulse Fast" in text
    assert "nyra_listening_white_fast" not in text
