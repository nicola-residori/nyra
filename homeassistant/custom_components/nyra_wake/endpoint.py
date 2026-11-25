"""Carry the start of command audio from wake to STT within one Assist run."""
from contextvars import ContextVar

command_offset = ContextVar("nyra_command_offset", default=None)


async def until_command_end(stream, skip, probability):
    """Forward the original PCM, scoring 10 ms frames after the wake timestamp."""
    pending = bytearray()
    voiced = 0
    silent = 0
    started = False
    async for chunk in stream:
        start = min(skip, len(chunk))
        skip -= start
        pending.extend(chunk[start:])
        # Include the received chunk in STT even when its final frames end speech.
        yield chunk
        complete = len(pending) // 320 * 320
        for offset in range(0, complete, 320):
            score = probability(bytes(pending[offset:offset + 320]))
            if score < 0:
                continue
            if score >= (0.4 if started else 0.3):
                voiced += 1
                silent = 0
                if voiced >= 16:
                    started = True
            else:
                silent += 1
                if not started and silent >= 6:
                    voiced = 0
                if started and silent >= 45:
                    return
        del pending[:complete]
