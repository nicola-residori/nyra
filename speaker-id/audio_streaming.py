"""Bounded stream sink for Speaker-ID; contains no Router dependencies."""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import io
import json
import sys
import sqlite3
from threading import BoundedSemaphore, Lock, RLock
import wave
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


_MODULE_LOCK = RLock()


def _module(name):
    # Works both in the repository's hyphenated directory and /opt/service.
    key = f'_nyra_speaker_stream_{name}'
    with _MODULE_LOCK:
        if key not in sys.modules:
            spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name(f'{name}.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[key] = module
            spec.loader.exec_module(module)
        return sys.modules[key]


_MODES = {'IDENTIFICATION': 'identification', 'ENROLLMENT': 'enrollment',
          'WAKE_WORD_CAPTURE': 'wake_word'}


class SpeakerAudioSink:
    def __init__(self, config_store, data_root, engine=None, max_stream_bytes=8 * 1024 * 1024):
        if max_stream_bytes <= 0:
            raise ValueError('max_stream_bytes must be positive')
        self.config_store = config_store
        self.data_root = Path(data_root)
        self.engine = engine
        self.max_stream_bytes = max_stream_bytes
        self._streams = {}
        self._inference_lock = Lock()
        self._processing_capacity = BoundedSemaphore(4)

    def active_stream_ids(self):
        return set(self._streams)

    async def start(self, metadata):
        stream_id = metadata.audio_stream_id
        if stream_id in self._streams:
            raise ValueError('DUPLICATE_STREAM')
        if metadata.purpose not in _MODES:
            raise ValueError('UNSUPPORTED_PURPOSE')
        self._streams[stream_id] = (
            copy.deepcopy(metadata), copy.deepcopy(self.config_store.identification_snapshot()), bytearray()
        )

    async def chunk(self, stream_id, data):
        state = self._streams.get(stream_id)
        if state is None:
            raise ValueError('UNKNOWN_STREAM')
        buffer = state[2]
        if len(buffer) + len(data) > self.max_stream_bytes:
            await self.abort(stream_id, 'STREAM_TOO_LARGE')
            raise ValueError('STREAM_TOO_LARGE')
        buffer.extend(data)

    async def abort(self, stream_id, reason):
        state = self._streams.pop(stream_id, None)
        if state is not None:
            state[2].clear()

    async def end(self, stream_id):
        state = self._streams.pop(stream_id, None)
        if state is None:
            raise ValueError('UNKNOWN_STREAM')
        metadata, snapshot, buffer = state
        try:
            if not self._processing_capacity.acquire(blocking=False):
                raise ValueError('PROCESSING_CAPACITY_EXCEEDED')
            try:
                worker = asyncio.get_running_loop().run_in_executor(
                    None, self._prepare_bounded, metadata, bytes(buffer))
            except BaseException:
                self._processing_capacity.release()
                raise
            # Keep queued work alive on caller cancellation so its finally releases
            # capacity; admission remains bounded until those workers really exit.
            prepared = await asyncio.shield(worker)
            # Durable writes run only after the cancellable computation completes.
            return self._process(metadata, snapshot, *prepared)
        finally:
            buffer.clear()

    def _prepare_bounded(self, metadata, raw):
        try:
            return self._prepare(metadata, raw)
        finally:
            self._processing_capacity.release()

    def _engine(self):
        if self.engine is None:
            self.engine = _module('embeddings').SpeechBrainECAPAEngine(
                savedir=str(self.data_root / 'models' / 'ecapa'))
        return self.engine

    @staticmethod
    def _wav(metadata, raw):
        audio_format = getattr(metadata, 'audio_format', 'wav')
        if audio_format == 'wav':
            try:
                with wave.open(io.BytesIO(raw), 'rb') as wav:
                    channels = wav.getnchannels()
                    sample_rate = wav.getframerate()
                    if channels not in (1, 2) or not 8000 <= sample_rate <= 96000 or wav.getsampwidth() != 2:
                        raise _module('preprocessing').AudioRejected('INVALID_AUDIO_FORMAT')
                    if wav.getnframes() > sample_rate * 30:
                        raise _module('preprocessing').AudioRejected('AUDIO_TOO_LONG')
            except (wave.Error, EOFError) as exc:
                raise _module('preprocessing').AudioRejected('INVALID_AUDIO') from exc
            return raw
        if audio_format != 'pcm_s16le':
            raise _module('preprocessing').AudioRejected('UNSUPPORTED_AUDIO_FORMAT')
        channels = getattr(metadata, 'channels', 1)
        sample_rate = getattr(metadata, 'sample_rate', 16000)
        if channels not in (1, 2) or not 8000 <= sample_rate <= 96000:
            raise _module('preprocessing').AudioRejected('INVALID_AUDIO_FORMAT')
        if len(raw) % (2 * channels):
            raise _module('preprocessing').AudioRejected('INVALID_AUDIO')
        if len(raw) // (2 * channels) > sample_rate * 30:
            raise _module('preprocessing').AudioRejected('AUDIO_TOO_LONG')
        result = io.BytesIO()
        with wave.open(result, 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(raw)
        return result.getvalue()

    def _prepare(self, metadata, raw):
        preprocessing = _module('preprocessing')
        mode = _MODES[metadata.purpose]
        processed = None
        reason = None
        embedding = None
        centroids = {}
        try:
            processed = preprocessing.preprocess_audio(self._wav(metadata, raw), mode=mode)
            if mode == 'identification':
                centroids = self._profile_centroids()
            if mode == 'enrollment' or centroids:
                with self._inference_lock:
                    embedding = self._engine().embed(processed)
        except preprocessing.AudioRejected as exc:
            reason = exc.reason_code
        except Exception:
            reason = 'PROCESSING_FAILED'
        return processed, embedding, reason, centroids

    def _process(self, metadata, snapshot, processed, embedding, reason, centroids):
        mode = _MODES[metadata.purpose]
        if mode == 'identification':
            return self._identify(processed, embedding, snapshot, reason, centroids)
        if mode == 'enrollment':
            if reason:
                return {'status': 'FAILED' if reason == 'PROCESSING_FAILED' else 'REJECTED', 'sample_id': None,
                        'user_id': metadata.user_id, 'reason_code': reason}
            try:
                store = _module('profiles').ProfileStore(self.data_root)
                store.initialize()
                sample = store.add_sample(
                    user_id=metadata.user_id, source_id=metadata.source_id,
                    wav_bytes=processed.wav_bytes, embedding=embedding,
                    quality=asdict(processed.quality),
                    preprocessing_version=processed.preprocessing_version)
                return {'status': 'ACCEPTED', 'sample_id': sample.sample_id, 'user_id': sample.user_id}
            except Exception:
                return {'status': 'FAILED', 'sample_id': None,
                        'user_id': metadata.user_id, 'reason_code': 'PROCESSING_FAILED'}
        store = _module('wake_words').WakeWordStore(self.data_root)
        store.initialize()
        try:
            return asdict(store.complete_capture(
                capture_id=metadata.wake_word_session_id, status='REJECTED' if reason else 'ACCEPTED',
                wake_word_text=metadata.wake_word_text, user_id=metadata.user_id,
                source_id=metadata.source_id, language=metadata.language,
                created_at=datetime.now(timezone.utc), processed_audio=processed, reason_code=reason))
        except Exception:
            return {'capture_id': metadata.wake_word_session_id, 'status': 'FAILED',
                    'sample_id': None, 'reason_code': 'PROCESSING_FAILED'}

    def _profile_centroids(self):
        db_path = self.data_root / 'speaker_id.sqlite3'
        if not db_path.exists():
            return {}
        with sqlite3.connect(f'{db_path.as_uri()}?mode=ro', uri=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='speaker_profiles'"
            ).fetchone()
            if not exists:
                return {}
            rows = connection.execute('SELECT user_id, centroid_json FROM speaker_profiles').fetchall()
        return {user_id: json.loads(centroid) for user_id, centroid in rows}

    def _identify(self, processed, embedding, snapshot, reason, centroids):
        identification = _module('identification')
        scores = {}
        if reason is None:
            try:
                if centroids:
                    scores = identification.cosine_scores(
                        query_embedding=embedding, profile_centroids=centroids)
                result = identification.classify_scores(scores, threshold=snapshot.threshold, margin=snapshot.margin)
            except Exception:
                reason = 'PROCESSING_FAILED'
        if reason:
            result = identification.failed_result(diagnostic_id=None, reason_code=reason)
        diagnostics = _module('diagnostics').DiagnosticStore(self.data_root)
        diagnostics.initialize()
        wav_path = None
        if processed is not None:
            wav_path = diagnostics.allocate_diagnostic_wav_path()
            wav_path.write_bytes(processed.wav_bytes)
        try:
            diagnostic_id = diagnostics.record(
                outcome=result.outcome.value, identified_user_id=result.identified_user_id,
                best_score=result.best_score, reason_code=result.reason_code,
                candidate_scores=scores, preprocessing_version=processed.preprocessing_version if processed else '1',
                model_revision='speechbrain/spkrec-ecapa-voxceleb', config_snapshot=snapshot,
                diagnostic_wav_path=wav_path)
        except Exception:
            if wav_path is not None:
                wav_path.unlink(missing_ok=True)
            raise
        payload = asdict(result)
        payload['outcome'] = result.outcome.value
        payload['diagnostic_id'] = diagnostic_id
        return payload
