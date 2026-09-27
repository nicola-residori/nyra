from pathlib import Path
S=Path("esphome/packages/nyra-speaker.yaml")
def t(): return S.read_text()
def test_optional_native_control():
    s=t(); assert "nyra_battery_percent" in s; assert 'name: "Nyra Battery Gauge Percent"' in s
    assert "optimistic: true" in s; assert "${battery_entity}" not in s; assert "platform: homeassistant" not in s
def test_circular_fixed_color_scale():
    s=t(); assert 'name: "nyra_battery_gauge"' in s and "it.size()" in s and "ceilf" in s
    for x in ("Color(255, 0, 0)","Color(255, 96, 0)","Color(255, 210, 0)","Color(0, 255, 0)","Color(0, 0, 0)"): assert x in s
def test_tracked_esphome_has_no_battery_entity_substitution():
    assert "battery_entity:" not in S.read_text()
