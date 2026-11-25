import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "homeassistant/custom_components"))
from nyra_wake.endpoint import until_command_end


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def run_clip(self, scores, skip_frames=0):
        voice = b"\x01\x00" * 160
        silence = bytes(320)
        pcm = b"".join(voice if v else silence for v in scores)
        async def chunks():
            for offset in range(0, len(pcm), 416):
                yield pcm[offset:offset + 416]
        out = b"".join([b async for b in until_command_end(chunks(), skip_frames * 320, lambda x: float(x[0] != 0))])
        self.assertEqual(out, pcm[:len(out)])
        return len(out) / 320

    async def test_joined_command_in_buffer_stops_after_silence(self):
        end = await self.run_clip([1]*45 + [1]*32 + [0]*200, 45)
        self.assertGreaterEqual(end, 122)
        self.assertLess(end, 124)

    async def test_pre_roll_does_not_end_a_paused_call(self):
        end = await self.run_clip([1]*60 + [0]*120 + [1]*48 + [0]*100, 60)
        self.assertGreaterEqual(end, 273)
        self.assertLess(end, 275)

    async def test_brief_pause_inside_a_command_preserves_audio(self):
        end = await self.run_clip([1]*30 + [0]*30 + [1]*25 + [0]*160)
        self.assertGreaterEqual(end, 130)
        self.assertLess(end, 132)
