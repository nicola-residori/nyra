from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SHARED = ROOT / "shared"
BUNDLED_SHARED = ROOT / "homeassistant" / "custom_components" / "nyra" / "shared"
BOOTSTRAP = ROOT / "homeassistant" / "custom_components" / "nyra" / "protocol_bootstrap.py"
INIT = ROOT / "homeassistant" / "custom_components" / "nyra" / "__init__.py"


def test_home_assistant_bundled_shared_protocol_matches_canonical():
    canonical = {
        path.relative_to(CANONICAL_SHARED)
        for path in (CANONICAL_SHARED / "protocol").glob("*.py")
    }
    bundled = {
        path.relative_to(BUNDLED_SHARED)
        for path in (BUNDLED_SHARED / "protocol").glob("*.py")
    }
    assert bundled == canonical
    assert (BUNDLED_SHARED / "__init__.py").read_text() == (
        CANONICAL_SHARED / "__init__.py"
    ).read_text()
    for relative in canonical:
        assert (BUNDLED_SHARED / relative).read_text() == (
            CANONICAL_SHARED / relative
        ).read_text()


def test_home_assistant_initializes_shared_protocol_before_client_import():
    source = INIT.read_text()
    bootstrap = source.index("ensure_shared_protocol()")
    client = source.index("from .client import")
    assert bootstrap < client


def test_bootstrap_exposes_bundled_protocol_under_canonical_module_name(tmp_path):
    package = tmp_path / "custom_components" / "nyra"
    package.mkdir(parents=True)
    (tmp_path / "custom_components" / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "protocol_bootstrap.py").write_text(BOOTSTRAP.read_text())

    import shutil
    shutil.copytree(BUNDLED_SHARED, package / "shared")

    site_packages = next(
        entry for entry in sys.path
        if entry and "site-packages" in entry
    )

    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(tmp_path)!r})\n"
        f"sys.path.append({site_packages!r})\n"
        "import importlib\n"
        "from custom_components.nyra.protocol_bootstrap import ensure_shared_protocol\n"
        "assert \"shared\" not in sys.modules\n"
        "ensure_shared_protocol()\n"
        "requests = importlib.import_module(\"shared.protocol.requests\")\n"
        "events = importlib.import_module(\"shared.protocol.events\")\n"
        "assert requests.ExecutionType.HA_SPEAKER.value == \"ha_speaker\"\n"
        "assert events.InteractionState.PROCESSING_GLOBAL.value == \"PROCESSING_GLOBAL\"\n"
        "assert sys.modules[\"shared\"].__name__ == \"custom_components.nyra.shared\"\n"
        "assert sys.modules[\"shared.protocol\"].__name__ == \"shared.protocol\"\n"
    )

    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr

def test_bootstrap_preserves_existing_canonical_shared_protocol_identity():
    code = """
from shared.protocol.requests import ExecutionType as before
from homeassistant.custom_components.nyra.protocol_bootstrap import ensure_shared_protocol
ensure_shared_protocol()
from shared.protocol.requests import ExecutionType as after
assert before is after
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
