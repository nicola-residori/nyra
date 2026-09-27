from pathlib import Path
S=Path("esphome/packages/nyra-speaker.yaml")
def t(): return S.read_text()
def test_optional_native_control():
    s=t(); assert "nyra_battery_percent" in s; assert 'name: "Nyra Battery Gauge Percent"' in s
    assert "optimistic: true" in s; assert "${battery_entity}" not in s; assert "platform: homeassistant" not in s
def test_front_led_gauge_contract():
    s=t()
    assert 'name: "nyra_battery_gauge"' in s
    for x in ("const int left = 1;", "const int center = 0;", "const int right = n - 1;",
              "it.all() = Color(0, 0, 0);", "pct <= 5.0f", "pct <= 10.0f",
              "pct <= 15.0f", "pct <= 20.0f", "pct <= 30.0f", "pct <= 40.0f",
              "pct <= 60.0f", "pct <= 80.0f",
              "Color(255, 0, 0)", "Color(255, 210, 0)", "Color(0, 255, 0)"):
        assert x in s
def test_tracked_esphome_has_no_battery_entity_substitution():
    assert "battery_entity:" not in S.read_text()
