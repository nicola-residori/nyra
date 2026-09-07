from __future__ import annotations

import os
import sqlite3
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from time import monotonic

from fastapi import FastAPI, HTTPException, Response, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from shared.audio_streaming import AudioStreamRegistry
from shared.audio_websocket import serve_audio
import importlib.util
import sys
from datetime import datetime, timezone
from pydantic import BaseModel, Field


DEFAULT_DATA_ROOT = Path("/var/lib/nyra-speaker-id")
DEFAULT_THRESHOLD = 0.40
DEFAULT_MARGIN = 0.07
CONFIG_VERSION = 1


@dataclass(frozen=True)
class IdentificationConfigSnapshot:
    threshold: float
    margin: float
    revision: int


class IdentificationConfigUpdate(BaseModel):
    threshold: float = Field(ge=-1.0, le=1.0)
    margin: float = Field(ge=0.0, le=2.0)


class SampleSelection(BaseModel):
    sample_ids: list[str]


class SQLiteConfigStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self._lock = Lock()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_config (
                    key TEXT PRIMARY KEY,
                    threshold REAL NOT NULL,
                    margin REAL NOT NULL,
                    revision INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO runtime_config
                    (key, threshold, margin, revision)
                VALUES ('identification', ?, ?, 1)
                """,
                (DEFAULT_THRESHOLD, DEFAULT_MARGIN),
            )

    def identification_snapshot(self) -> IdentificationConfigSnapshot:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT threshold, margin, revision
                FROM runtime_config
                WHERE key = 'identification'
                """
            ).fetchone()
        if row is None:
            raise RuntimeError("identification config is not initialized")
        return IdentificationConfigSnapshot(
            threshold=float(row[0]),
            margin=float(row[1]),
            revision=int(row[2]),
        )

    def update_identification(
        self, threshold: float, margin: float
    ) -> IdentificationConfigSnapshot:
        with self._lock:
            with self._connect() as connection:
                current = connection.execute(
                    """
                    SELECT revision
                    FROM runtime_config
                    WHERE key = 'identification'
                    """
                ).fetchone()
                if current is None:
                    raise RuntimeError("identification config is not initialized")
                revision = int(current[0]) + 1
                connection.execute(
                    """
                    UPDATE runtime_config
                    SET threshold = ?, margin = ?, revision = ?
                    WHERE key = 'identification'
                    """,
                    (threshold, margin, revision),
                )
        return IdentificationConfigSnapshot(threshold, margin, revision)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)


def create_app(
    data_root: str | Path | None = None,
    *,
    embedding_engine=None,
) -> FastAPI:
    root = Path(
        data_root
        if data_root is not None
        else os.getenv("NYRA_SPEAKER_ID_DATA_ROOT", DEFAULT_DATA_ROOT)
    )
    store = SQLiteConfigStore(root / "speaker-id.sqlite3")
    started = monotonic()
    module_name = "nyra_speaker_audio_streaming"
    module_spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name("audio_streaming.py"))
    streaming = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = streaming
    module_spec.loader.exec_module(streaming)
    audio_sink = streaming.SpeakerAudioSink(store, root, engine=embedding_engine)
    wake_words = streaming._module("wake_words")
    wake_word_store = wake_words.WakeWordStore(root)
    profiles = streaming._module("profiles")
    diagnostics = streaming._module("diagnostics")
    wake_word_export = streaming._module("wake_word_export")
    profile_store = profiles.ProfileStore(root)
    diagnostic_store = diagnostics.DiagnosticStore(root)
    audio_streams = AudioStreamRegistry(audio_sink, float(os.getenv("NYRA_AUDIO_STREAM_TIMEOUT_SECONDS", "30")))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        root.mkdir(parents=True, exist_ok=True)
        (root / "audio").mkdir(exist_ok=True)
        store.initialize()
        wake_word_store.initialize()
        profile_store.initialize()
        diagnostic_store.initialize()
        diagnostics.DiagnosticHousekeeper(diagnostic_store).cleanup()
        app.state.storage_ready = True
        try:
            await asyncio.to_thread(audio_sink.prepare_model)
        except Exception:
            app.state.model_state = "unavailable"
        else:
            app.state.model_state = "loaded"
            app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            await app.state.audio_streams.close()

    app = FastAPI(title="Nyra Speaker ID", lifespan=lifespan)
    app.state.audio_streams = audio_streams
    app.state.audio_sink = audio_sink
    app.state.data_root = root
    app.state.config_store = store
    app.state.wake_word_store = wake_word_store
    app.state.profile_store = profile_store
    app.state.diagnostic_store = diagnostic_store
    app.state.ready = False
    app.state.storage_ready = False
    app.state.model_state = "not_loaded"

    @app.websocket("/v1/audio/stream")
    async def audio_stream(websocket: WebSocket):
        await serve_audio(websocket, app.state.audio_streams)

    @app.get("/health")
    def health():
        return {
            "service": "nyra-speaker-id",
            "status": "healthy",
            "uptime": round(monotonic() - started, 3),
        }

    @app.get("/ready")
    def ready():
        payload = {
            "ready": bool(app.state.ready),
            "storage": "initialized" if app.state.storage_ready else "not_initialized",
            "model": app.state.model_state,
        }
        if app.state.ready:
            return payload
        return JSONResponse(payload, status_code=503)

    @app.get("/v1/config")
    def get_config():
        snapshot = store.identification_snapshot()
        return {
            "version": CONFIG_VERSION,
            "identification": asdict(snapshot),
        }

    @app.put("/v1/config/identification")
    def put_identification_config(update: IdentificationConfigUpdate):
        return asdict(
            store.update_identification(
                threshold=update.threshold,
                margin=update.margin,
            )
        )

    @app.get("/v1/wake-word-samples/count")
    def wake_word_sample_count(wake_word_text: str):
        normalized = " ".join(wake_word_text.strip().split())
        if not normalized:
            return JSONResponse({"detail": "wake_word_text is required"}, status_code=422)
        return {
            "wake_word_text": normalized,
            "sample_count": wake_word_store.count_samples(normalized),
        }

    def enrollment_sample_payload(sample):
        return {
            "sample_id": sample.sample_id, "user_id": sample.user_id,
            "source_id": sample.source_id, "created_at": sample.created_at,
            "duration_seconds": sample.duration_seconds, "quality": sample.quality,
            "preprocessing_version": sample.preprocessing_version,
        }

    @app.get("/v1/admin/profiles")
    def admin_profiles():
        return [{
            "user_id": profile.user_id, "sample_count": profile.sample_count,
            "samples": [enrollment_sample_payload(sample)
                        for sample in profile_store.list_samples(profile.user_id)],
        } for profile in profile_store.list_profiles()]

    @app.get("/v1/admin/profiles/{user_id}/samples/{sample_id}/audio")
    def enrollment_audio(user_id: str, sample_id: str):
        sample = profile_store.get_sample(user_id, sample_id)
        if sample is None or not Path(sample.wav_path).is_file():
            raise HTTPException(status_code=404, detail="enrollment audio not found")
        return FileResponse(sample.wav_path, media_type="audio/wav")

    @app.delete("/v1/admin/profiles/{user_id}/samples")
    def delete_enrollment_samples(user_id: str, selection: SampleSelection):
        return {"deleted": profile_store.delete_samples(user_id, selection.sample_ids)}

    @app.delete("/v1/admin/profiles/{user_id}")
    def delete_profile(user_id: str):
        return {"deleted": profile_store.delete_profile(user_id)}

    def diagnostic_details_available(record):
        return bool(
            record.detail_expires_at
            and record.detail_expires_at > datetime.now(timezone.utc)
        )

    def diagnostic_payload(record):
        details_available = diagnostic_details_available(record)
        audio_available = bool(
            details_available
            and record.diagnostic_wav_path
            and Path(record.diagnostic_wav_path).is_file()
        )
        return {
            "diagnostic_id": record.diagnostic_id, "created_at": record.created_at,
            "source_id": record.source_id, "outcome": record.outcome,
            "identified_user_id": record.identified_user_id, "best_score": record.best_score,
            "reason_code": record.reason_code, "preprocessing_version": record.preprocessing_version,
            "model_revision": record.model_revision, "config_revision": record.config_revision,
            "threshold": record.threshold, "margin": record.margin,
            "request_id": record.request_id, "session_id": record.session_id,
            "trace_id": record.trace_id, "span_id": record.span_id,
            "detail_expires_at": record.detail_expires_at,
            "details_available": details_available, "audio_available": audio_available,
        }

    @app.get("/v1/admin/diagnostics")
    def admin_diagnostics(source_id: str | None = None, outcome: str | None = None,
                          user_id: str | None = None, limit: int = 100):
        return [diagnostic_payload(record) for record in diagnostic_store.list(
            source_id=source_id, outcome=outcome, user_id=user_id, limit=limit
        )]

    @app.get("/v1/admin/diagnostics/{diagnostic_id}/audio")
    def diagnostic_audio(diagnostic_id: str):
        record = diagnostic_store.get(diagnostic_id)
        if (record is None or not diagnostic_details_available(record)
                or not record.diagnostic_wav_path or not Path(record.diagnostic_wav_path).is_file()):
            raise HTTPException(status_code=404, detail="diagnostic audio expired or unavailable")
        return FileResponse(record.diagnostic_wav_path, media_type="audio/wav")

    @app.get("/v1/admin/diagnostics/{diagnostic_id}")
    def diagnostic_detail(diagnostic_id: str):
        record = diagnostic_store.get(diagnostic_id)
        if record is None:
            raise HTTPException(status_code=404, detail="diagnostic not found")
        available = diagnostic_details_available(record)
        return {
            **diagnostic_payload(record),
            "candidates": ([asdict(item) for item in diagnostic_store.list_candidates(diagnostic_id)]
                           if available else []),
        }

    def wake_word_payload(sample):
        return {
            "sample_id": sample.sample_id, "capture_id": sample.capture_id,
            "wake_word_id": sample.wake_word_id, "wake_word_text": sample.wake_word_text,
            "user_id": sample.user_id, "source_id": sample.source_id,
            "language": sample.language, "created_at": sample.created_at,
            "duration_seconds": sample.duration_seconds, "quality": sample.quality,
            "preprocessing_version": sample.preprocessing_version,
        }

    @app.get("/v1/admin/wake-words")
    def admin_wake_words(wake_word_text: str | None = None, user_id: str | None = None,
                         source_id: str | None = None):
        samples = wake_word_store.list_samples(wake_word_text)
        if user_id:
            samples = [sample for sample in samples if sample.user_id == user_id]
        if source_id:
            samples = [sample for sample in samples if sample.source_id == source_id]
        return [wake_word_payload(sample) for sample in samples]

    @app.get("/v1/admin/wake-words/samples/{sample_id}/audio")
    def wake_word_audio(sample_id: str):
        sample = wake_word_store.get_sample(sample_id)
        if sample is None or not Path(sample.wav_path).is_file():
            raise HTTPException(status_code=404, detail="wake-word audio not found")
        return FileResponse(sample.wav_path, media_type="audio/wav")

    @app.delete("/v1/admin/wake-words/samples")
    def delete_wake_word_samples(selection: SampleSelection):
        return {"deleted": wake_word_store.delete_samples(selection.sample_ids)}

    @app.post("/v1/admin/wake-words/export")
    def export_wake_word_samples(selection: SampleSelection):
        try:
            archive = wake_word_export.export_samples(wake_word_store, selection.sample_ids)
        except wake_word_export.UnknownWakeWordSample as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            archive, media_type="application/gzip",
            headers={"Content-Disposition": "attachment; filename=wake-word-samples.tar.gz"},
        )

    return app


app = create_app()
