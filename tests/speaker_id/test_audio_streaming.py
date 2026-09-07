import asyncio
import importlib.util
import io
import sys
import wave
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_sink():
    path = Path(__file__).parents[2] / 'speaker-id' / 'audio_streaming.py'
    assert path.exists(), 'SpeakerAudioSink implementation is missing'
    spec = importlib.util.spec_from_file_location('speaker_streaming_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.SpeakerAudioSink


class Purpose(str, Enum):
    IDENTIFICATION = 'IDENTIFICATION'
    ENROLLMENT = 'ENROLLMENT'
    WAKE_WORD_CAPTURE = 'WAKE_WORD_CAPTURE'


def metadata(stream='s1', purpose=Purpose.IDENTIFICATION, **kwargs):
    return SimpleNamespace(audio_stream_id=stream, purpose=purpose, user_id='nicola',
        source_id='mic', language='it', enrollment_session_id='enroll',
        wake_word_session_id='wake', wake_word_text='Nyra', **kwargs)


class Config:
    threshold = 0.4
    def identification_snapshot(self):
        return SimpleNamespace(threshold=self.threshold, margin=.07, revision=1)


class Engine:
    def embed(self, audio):
        assert audio.wav_bytes.startswith(b'RIFF')
        return [.8, .6]


def wav_bytes():
    result = io.BytesIO()
    with wave.open(result, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b'\x00\x20' * 8000)
    return result.getvalue()


def test_bound_abort_and_missing_stream(tmp_path):
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=Engine(), max_stream_bytes=3)
        await sink.start(metadata())
        await sink.chunk('s1', b'123')
        with pytest.raises(ValueError, match='STREAM_TOO_LARGE'):
            await sink.chunk('s1', b'4')
        assert sink.active_stream_ids() == set()
        await sink.start(metadata())
        await sink.abort('s1', 'DISCONNECTED')
        await sink.abort('s1', 'DISCONNECTED')
        assert sink.active_stream_ids() == set()
        assert not list(tmp_path.rglob('*.wav'))
        with pytest.raises(ValueError, match='UNKNOWN_STREAM'):
            await sink.end('s1')
    asyncio.run(run())


def test_malformed_identification_has_failed_diagnostic_and_cleans_buffer(tmp_path):
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=Engine())
        await sink.start(metadata())
        await sink.chunk('s1', b'bad')
        result = await sink.end('s1')
        assert result['outcome'] == 'FAILED'
        assert result['reason_code'] == 'INVALID_AUDIO'
        assert result['diagnostic_id']
        assert sink.active_stream_ids() == set()
    asyncio.run(run())


def test_typed_enrollment_then_identification_snapshots_config(tmp_path):
    async def run():
        config = Config()
        sink = load_sink()(config, tmp_path, engine=Engine())
        await sink.start(metadata('enroll', Purpose.ENROLLMENT))
        await sink.chunk('enroll', wav_bytes())
        enrolled = await sink.end('enroll')
        assert enrolled['status'] == 'ACCEPTED'
        assert enrolled['user_id'] == 'nicola'
        assert enrolled['sample_id']
        await sink.start(metadata())
        config.threshold = 1.1
        await sink.chunk('s1', wav_bytes())
        result = await sink.end('s1')
        assert result['outcome'] == 'IDENTIFIED'
        assert result['identified_user_id'] == 'nicola'
        assert set(result) == {'outcome', 'identified_user_id', 'best_score', 'diagnostic_id', 'reason_code'}
        assert sink.active_stream_ids() == set()
    asyncio.run(run())


def test_wake_word_pcm_capture_persists_sample(tmp_path):
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=Engine())
        await sink.start(metadata('wake1', Purpose.WAKE_WORD_CAPTURE, audio_format='pcm_s16le', sample_rate=16000, channels=1))
        await sink.chunk('wake1', b'\x00\x20' * 8000)
        result = await sink.end('wake1')
        assert result['status'] == 'ACCEPTED'
        assert result['capture_id'] == 'wake'
        assert result['sample_id']
        assert len(list((tmp_path / 'wake_words').rglob('*.wav'))) == 1
    asyncio.run(run())


def test_invalid_purpose_and_duplicate_start_do_not_replace_audio(tmp_path):
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=Engine())
        with pytest.raises(ValueError, match='UNSUPPORTED_PURPOSE'):
            await sink.start(metadata(purpose='other'))
        await sink.start(metadata())
        await sink.chunk('s1', wav_bytes())
        with pytest.raises(ValueError, match='DUPLICATE_STREAM'):
            await sink.start(metadata())
        assert (await sink.end('s1'))['outcome'] == 'NOT_RECOGNIZED'
    asyncio.run(run())


def test_embedding_failure_returns_failed_and_cleans_stream(tmp_path):
    class BrokenEngine:
        def embed(self, audio):
            raise RuntimeError('engine offline')
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=Engine())
        await sink.start(metadata('seed', Purpose.ENROLLMENT))
        await sink.chunk('seed', wav_bytes())
        assert (await sink.end('seed'))['status'] == 'ACCEPTED'
        sink.engine = BrokenEngine()
        await sink.start(metadata())
        await sink.chunk('s1', wav_bytes())
        result = await sink.end('s1')
        assert result['outcome'] == 'FAILED'
        assert result['reason_code'] == 'PROCESSING_FAILED'
        assert sink.active_stream_ids() == set()
    asyncio.run(run())


def test_ecapa_adapter_decodes_pcm_wav_without_torchaudio_or_model_download(monkeypatch):
    path = Path(__file__).parents[2] / 'speaker-id' / 'embeddings.py'
    spec = importlib.util.spec_from_file_location('speaker_embedding_stream_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from contextlib import nullcontext
    class Waveform:
        def unsqueeze(self, dimension):
            assert dimension == 0
            return self
        def __truediv__(self, value):
            assert value == 32768.0
            return self
    def tensor(samples, dtype):
        assert len(samples) == 8000
        assert dtype == 'float32'
        return Waveform()
    class Vector:
        def squeeze(self): return self
        def detach(self): return self
        def cpu(self): return self
        def tolist(self): return [.8, .6]
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        no_grad=nullcontext, tensor=tensor, float32='float32'))
    monkeypatch.setitem(sys.modules, 'torchaudio', None)
    engine = module.SpeechBrainECAPAEngine()
    engine._classifier = SimpleNamespace(encode_batch=lambda waveform: Vector())
    assert engine.embed(SimpleNamespace(wav_bytes=wav_bytes(), sample_rate=16000)) == [.8, .6]


def test_cancelled_end_cannot_persist_after_embedding_finishes(tmp_path):
    import threading
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    class SlowEngine:
        def embed(self, audio):
            entered.set()
            release.wait(5)
            finished.set()
            return [.8, .6]
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=SlowEngine())
        await sink.start(metadata('enroll', Purpose.ENROLLMENT))
        await sink.chunk('enroll', wav_bytes())
        ending = asyncio.create_task(sink.end('enroll'))
        assert await asyncio.to_thread(entered.wait, 5)
        ending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await ending
        release.set()
        assert await asyncio.to_thread(finished.wait, 5)
        assert sink.active_stream_ids() == set()
    asyncio.run(run())  # waits for the worker to fully exit before inspecting durable files
    assert not list(tmp_path.rglob('*.wav'))



def test_wake_session_accepts_at_most_one_sample_across_streams(tmp_path):
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=Engine())
        for stream in ('one', 'two'):
            await sink.start(metadata(stream, Purpose.WAKE_WORD_CAPTURE))
            await sink.chunk(stream, wav_bytes())
            result = await sink.end(stream)
            if stream == 'one':
                assert result['status'] == 'ACCEPTED'
            else:
                assert result['status'] == 'FAILED'
        assert len(list((tmp_path / 'wake_words').rglob('*.wav'))) == 1
    asyncio.run(run())


def test_zero_profiles_does_not_require_embedding_engine(tmp_path):
    class UnavailableEngine:
        def embed(self, audio):
            raise RuntimeError('model unavailable')
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=UnavailableEngine())
        await sink.start(metadata())
        await sink.chunk('s1', wav_bytes())
        result = await sink.end('s1')
        assert result['outcome'] == 'NOT_RECOGNIZED'
        assert result['reason_code'] == 'NO_PROFILES'
    asyncio.run(run())


def test_concurrent_enrollments_serialize_shared_embedding_engine(tmp_path):
    import threading
    class NonReentrantEngine:
        busy = threading.Lock()
        def embed(self, audio):
            if not self.busy.acquire(blocking=False):
                raise RuntimeError('concurrent model inference')
            try:
                threading.Event().wait(.05)
                return [.8, .6]
            finally:
                self.busy.release()
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=NonReentrantEngine())
        for stream in ('one', 'two'):
            await sink.start(metadata(stream, Purpose.ENROLLMENT))
            await sink.chunk(stream, wav_bytes())
        results = await asyncio.gather(sink.end('one'), sink.end('two'))
        assert [result['status'] for result in results] == ['ACCEPTED', 'ACCEPTED']
    asyncio.run(run())


def test_concurrent_module_load_never_exposes_partial_module(monkeypatch):
    import concurrent.futures
    import threading
    load_sink()
    module = sys.modules['speaker_streaming_test']
    entered = threading.Event()
    release = threading.Event()
    class Loader:
        def create_module(self, spec): return None
        def exec_module(self, target):
            entered.set()
            release.wait(2)
            target.ready = True
    monkeypatch.setattr(module.importlib.util, 'spec_from_file_location',
                        lambda key, path: importlib.util.spec_from_loader(key, Loader()))
    key = '_nyra_speaker_stream_concurrency_probe'
    sys.modules.pop(key, None)
    def use_module():
        return module._module('concurrency_probe').ready
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            first = executor.submit(use_module)
            assert entered.wait(2)
            second = executor.submit(use_module)
            # Without a guard the second caller reads the incomplete module immediately.
            try:
                second.result(timeout=.05)
            except concurrent.futures.TimeoutError:
                pass
            finally:
                release.set()
            assert first.result(timeout=2) is True
            assert second.result(timeout=2) is True
    finally:
        sys.modules.pop(key, None)


def test_cancelled_processing_keeps_capacity_until_workers_exit(tmp_path):
    import threading
    entered = threading.Event()
    release = threading.Event()
    class BlockingEngine:
        def embed(self, audio):
            entered.set()
            release.wait(5)
            return [.8, .6]
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=BlockingEngine())
        endings = []
        for index in range(4):
            stream = str(index)
            await sink.start(metadata(stream, Purpose.ENROLLMENT))
            await sink.chunk(stream, wav_bytes())
            endings.append(asyncio.create_task(sink.end(stream)))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            for task in endings:
                task.cancel()
            await asyncio.gather(*endings, return_exceptions=True)
            await sink.start(metadata('overflow', Purpose.ENROLLMENT))
            await sink.chunk('overflow', wav_bytes())
            with pytest.raises(ValueError, match='PROCESSING_CAPACITY_EXCEEDED'):
                await sink.end('overflow')
        finally:
            release.set()
    asyncio.run(run())
    assert not list(tmp_path.rglob('*.wav'))


@pytest.mark.parametrize('rate,channels,frames,reason', [
    (1, 1, 2, 'INVALID_AUDIO_FORMAT'),
    (96001, 1, 2, 'INVALID_AUDIO_FORMAT'),
    (16000, 3, 2, 'INVALID_AUDIO_FORMAT'),
    (16000, 1, 16000 * 31, 'AUDIO_TOO_LONG'),
])
def test_wav_header_cannot_bypass_decode_bounds(tmp_path, rate, channels, frames, reason):
    data = io.BytesIO()
    with wave.open(data, 'wb') as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b'\x00\x20' * channels * 2)
    raw = bytearray(data.getvalue())
    raw[40:44] = (frames * channels * 2).to_bytes(4, 'little')
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=Engine())
        await sink.start(metadata())
        await sink.chunk('s1', bytes(raw))
        result = await sink.end('s1')
        assert result['outcome'] == 'FAILED'
        assert result['reason_code'] == reason
        assert not list(tmp_path.rglob('*.wav'))
    asyncio.run(run())


def test_pcm_decoded_duration_is_bounded(tmp_path):
    async def run():
        sink = load_sink()(Config(), tmp_path, engine=Engine())
        await sink.start(metadata(audio_format='pcm_s16le', sample_rate=16000, channels=1))
        await sink.chunk('s1', b'\x00\x20' * (16000 * 30 + 1))
        result = await sink.end('s1')
        assert result['outcome'] == 'FAILED'
        assert result['reason_code'] == 'AUDIO_TOO_LONG'
    asyncio.run(run())
