from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_branding_is_wired_to_readme_admin_and_home_assistant():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "assets/branding/nyra-banner.png" in readme

    for path in (
        "assets/branding/nyra-poster.png",
        "assets/branding/nyra-banner.png",
        "assets/branding/nyra-mark.png",
        "admin/static/img/nyra.png",
        "homeassistant/custom_components/nyra/brand/icon.png",
        "homeassistant/custom_components/nyra/brand/logo.png",
    ):
        assert (ROOT / path).is_file(), path
