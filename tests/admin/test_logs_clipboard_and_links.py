from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_logs_copy_supports_insecure_http_fallback():
    js = (ROOT / "admin/static/js/logs.js").read_text(encoding="utf-8")

    assert "function writeClipboard" in js
    assert "navigator.clipboard" in js
    assert "document.execCommand('copy')" in js or 'document.execCommand("copy")' in js
    assert "await writeClipboard" in js


def test_admin_content_links_have_explicit_dark_theme_contrast():
    css = (ROOT / "admin/static/css/admin.css").read_text(encoding="utf-8").replace(" ", "")

    assert "maina{" in css
    assert "maina:hover{" in css
    assert "maina:visited{" in css
