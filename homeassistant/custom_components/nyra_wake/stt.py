"""Preserve the configured Italian cloud transcriber and endpoint buffered speech."""
from contextlib import aclosing

from homeassistant.components import stt
from pymicro_vad import MicroVad

from .endpoint import command_offset, until_command_end


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([NyraCommandSTT(entry)])


class NyraCommandSTT(stt.SpeechToTextEntity):
    _attr_name = "Nyra command STT"

    def __init__(self, entry):
        self._attr_unique_id = entry.entry_id + "-command-stt"
        self.backend_id = entry.options.get("stt_backend", "stt.home_assistant_cloud")

    @property
    def backend(self):
        return stt.async_get_speech_to_text_engine(self.hass, self.backend_id)

    @property
    def supported_languages(self):
        backend = self.backend
        return backend.supported_languages if backend is not None else []

    @property
    def supported_formats(self):
        return [stt.AudioFormats.WAV]

    @property
    def supported_codecs(self):
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self):
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self):
        return [stt.AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self):
        return [stt.AudioChannels.CHANNEL_MONO]

    @property
    def audio_processing(self):
        backend = self.backend
        return backend.audio_processing if backend is not None else super().audio_processing

    async def async_process_audio_stream_with_progress(self, metadata, stream):
        backend = self.backend
        if backend is None:
            raise RuntimeError(f"Unavailable speech-to-text provider: {self.backend_id}")
        skip = command_offset.get()
        command_offset.set(None)
        if skip is not None:
            stream = until_command_end(stream, skip, MicroVad().Process10ms)
        async with aclosing(backend.internal_async_process_audio_stream_with_progress(metadata, stream)) as results:
            async for result in results:
                yield result
