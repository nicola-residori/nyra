from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).parents[2]


def load_module(filename: str, name: str):
    path = ROOT / "speaker-id" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class ConfigSnapshot:
    threshold: float = .40
    margin: float = .07
    revision: int = 1


class Clock:
    def __init__(self, now: datetime):
        self.current = now

    def now(self) -> datetime:
        return self.current


def create_detail(store, *, outcome: str, created_at: datetime, with_wav: bool = True) -> tuple[str, Path | None]:
    wav_path = None
    if with_wav:
        wav_path = store.allocate_diagnostic_wav_path()
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(b"processed-wav")

    diagnostic_id = store.record(
        outcome=outcome,
        identified_user_id="alice" if outcome == "IDENTIFIED" else None,
        best_score=.88 if outcome == "IDENTIFIED" else .39,
        reason_code=None if outcome == "IDENTIFIED" else "BELOW_THRESHOLD",
        candidate_scores={"alice": .88, "bob": .42},
        preprocessing_version="prep-1",
        model_revision="ecapa-r1",
        config_snapshot=ConfigSnapshot(),
        created_at=created_at,
        diagnostic_wav_path=wav_path,
    )
    return diagnostic_id, wav_path


def test_identified_detail_survives_14_59_and_expires_at_15_00(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_retention_identified")
    created = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)
    clock = Clock(created + timedelta(minutes=14, seconds=59))

    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()
    diagnostic_id, wav_path = create_detail(store, outcome="IDENTIFIED", created_at=created)

    housekeeper = diagnostics.DiagnosticHousekeeper(store, clock=clock.now)
    first = housekeeper.cleanup()

    assert first.expired_diagnostics == 0
    assert len(store.list_candidates(diagnostic_id)) == 2
    assert wav_path is not None and wav_path.exists()
    assert store.get(diagnostic_id) is not None

    clock.current = created + timedelta(minutes=15)
    second = housekeeper.cleanup()

    assert second.expired_diagnostics == 1
    assert store.list_candidates(diagnostic_id) == []
    assert wav_path is not None and not wav_path.exists()

    synthetic = store.get(diagnostic_id)
    assert synthetic is not None
    assert synthetic.outcome == "IDENTIFIED"
    assert synthetic.identified_user_id == "alice"
    assert synthetic.best_score == .88


def test_not_recognized_detail_survives_23_59_and_expires_at_24_00(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_retention_not_recognized")
    created = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)
    clock = Clock(created + timedelta(hours=23, minutes=59))

    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()
    diagnostic_id, wav_path = create_detail(store, outcome="NOT_RECOGNIZED", created_at=created)

    housekeeper = diagnostics.DiagnosticHousekeeper(store, clock=clock.now)
    housekeeper.cleanup()

    assert len(store.list_candidates(diagnostic_id)) == 2
    assert wav_path is not None and wav_path.exists()

    clock.current = created + timedelta(hours=24)
    result = housekeeper.cleanup()

    assert result.expired_diagnostics == 1
    assert store.list_candidates(diagnostic_id) == []
    assert wav_path is not None and not wav_path.exists()
    assert store.get(diagnostic_id) is not None


def test_failed_detail_uses_24_hour_retention(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_retention_failed")
    created = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)

    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()
    diagnostic_id, wav_path = create_detail(store, outcome="FAILED", created_at=created)

    clock = Clock(created + timedelta(hours=24))
    result = diagnostics.DiagnosticHousekeeper(store, clock=clock.now).cleanup()

    assert result.expired_diagnostics == 1
    assert store.list_candidates(diagnostic_id) == []
    assert wav_path is not None and not wav_path.exists()
    assert store.get(diagnostic_id) is not None


def test_cleanup_is_idempotent(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_retention_idempotent")
    created = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)

    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()
    diagnostic_id, wav_path = create_detail(store, outcome="IDENTIFIED", created_at=created)

    clock = Clock(created + timedelta(minutes=15))
    housekeeper = diagnostics.DiagnosticHousekeeper(store, clock=clock.now)

    first = housekeeper.cleanup()
    second = housekeeper.cleanup()

    assert first.expired_diagnostics == 1
    assert second.expired_diagnostics == 0
    assert second.deleted_wavs == 0
    assert store.list_candidates(diagnostic_id) == []
    assert wav_path is not None and not wav_path.exists()
    assert store.get(diagnostic_id) is not None


def test_cleanup_removes_orphan_temp_files(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_retention_orphans")
    created = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)

    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()

    orphan = store.diagnostic_temp_dir / "orphan.tmp"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"partial")

    active = store.diagnostic_temp_dir / "fresh.tmp"
    active.write_bytes(b"recent")

    old = created - timedelta(hours=2)
    diagnostics.set_file_mtime(orphan, old)
    diagnostics.set_file_mtime(active, created)

    clock = Clock(created + timedelta(minutes=30))
    result = diagnostics.DiagnosticHousekeeper(store, clock=clock.now).cleanup()

    assert result.deleted_orphan_temp_files == 1
    assert not orphan.exists()
    assert active.exists()


def test_record_persists_created_at_and_detail_expiry(tmp_path):
    diagnostics = load_module("diagnostics.py", "nyra_retention_metadata")
    created = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)

    store = diagnostics.DiagnosticStore(tmp_path)
    store.initialize()
    identified_id, _ = create_detail(store, outcome="IDENTIFIED", created_at=created, with_wav=False)
    failed_id, _ = create_detail(store, outcome="FAILED", created_at=created, with_wav=False)

    identified = store.get(identified_id)
    failed = store.get(failed_id)

    assert identified is not None
    assert identified.created_at == created
    assert identified.detail_expires_at == created + timedelta(minutes=15)

    assert failed is not None
    assert failed.created_at == created
    assert failed.detail_expires_at == created + timedelta(hours=24)
