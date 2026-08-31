from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pre_router_voice_phases_keep_nyra_listening_visual():
    text = (ROOT / "esphome/packages/nyra-speaker.yaml").read_text(encoding="utf-8")

    assert "voice_assistant:" in text
    for hook in ("on_listening:", "on_stt_vad_start:", "on_stt_vad_end:", "on_stt_end:"):
        assert hook in text
    assert text.count('effect: "nyra_listening_white_fast"') >= 4
