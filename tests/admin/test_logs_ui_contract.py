from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_logs_ui_has_presets_input_and_persistent_correlated_detail():
    html = (ROOT / "admin/templates/logs.html").read_text(encoding="utf-8")
    js = (ROOT / "admin/static/js/logs.js").read_text(encoding="utf-8")
    css = (ROOT / "admin/static/css/admin.css").read_text(encoding="utf-8")

    for value in ("15m", "1h", "6h", "24h", "all"):
        assert f'data-range="{value}"' in html
    assert "<th>Input</th>" in html
    assert "logs-workspace" in html
    assert "detail-panel" in html
    assert "extractRequestText" in js
    assert "loadRequestDetail" in js
    assert "navigator.clipboard.writeText" in js
    assert "request_id" in js
    assert ".logs-workspace" in css
    assert "position:sticky" in css
