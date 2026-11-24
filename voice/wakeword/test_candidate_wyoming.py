import asyncio,unittest,json
from types import SimpleNamespace
from wyoming.audio import AudioStart,AudioChunk
from wyoming.info import Describe,Info
from wyoming.wake import Detect,Detection
from wyoming.error import Error
from wyoming.event import async_read_event
from candidate_wyoming import CandidateHandler,ReadyEngines,diagnostic_snapshot
class Writer:
 def __init__(self):self.data=bytearray()
 def write(self,b):self.data.extend(b)
 def writelines(self,lines):
  for b in lines:self.write(b)
 async def drain(self):pass
class FakeEngine:
 def __init__(self):self.reset()
 def reset(self):self.chunks=[]
 def feed(self,b):
  import time;time.sleep(.03);self.chunks.append(b)
  return [dict(candidate_t=.08,t=.32,probability=.9)] if len(self.chunks)==1 else []
class Tests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.w=Writer();self.created=[]
  def factory():
   e=FakeEngine();self.created.append(e);return e
  self.h=CandidateHandler(asyncio.StreamReader(),self.w,factory)
 async def event(self):
  r=asyncio.StreamReader();r.feed_data(bytes(self.w.data));r.feed_eof();self.w.data.clear();return await async_read_event(r)
 def test_diagnostics_are_bounded_and_cannot_include_audio(self):
  engine=SimpleNamespace(samples=1280,ring=b'secret-pcm',candidates=[{'t':i,'probability':.5,'audio':b'secret-pcm'} for i in range(30)],detections=[])
  snapshot=diagnostic_snapshot([engine]);encoded=json.dumps(snapshot)
  self.assertEqual(len(snapshot[0]['candidates']),12)
  self.assertNotIn('secret',encoded);self.assertNotIn('"audio":',encoded);self.assertNotIn('ring',encoded)
 def test_preloaded_engines_are_reused_and_capacity_is_bounded(self):
  a,b=FakeEngine(),FakeEngine();pool=ReadyEngines([a,b])
  self.assertIs(pool.acquire(),a);self.assertIs(pool.acquire(),b)
  with self.assertRaises(RuntimeError):pool.acquire()
  pool.release(a);self.assertIs(pool.acquire(),a)
 async def test_describe_does_not_allocate_model(self):
  await self.h.handle_event(Describe().event());e=await self.event();self.assertTrue(Info.is_type(e.type));self.assertEqual(len(self.created),0)
 async def test_fragmented_pcm_preserves_detection_audio_timestamp(self):
  await self.h.handle_event(Detect(names=['ehi_nira_it']).event());await self.h.handle_event(AudioStart(rate=16000,width=2,channels=1).event())
  await self.h.handle_event(AudioChunk(rate=16000,width=2,channels=1,audio=bytes(1000),timestamp=5000).event());self.assertFalse(self.w.data)
  task=asyncio.create_task(self.h.handle_event(AudioChunk(rate=16000,width=2,channels=1,audio=bytes(1560),timestamp=5031).event()))
  await asyncio.sleep(.005);self.assertFalse(task.done());await task
  d=Detection.from_event(await self.event());self.assertEqual(d.timestamp,5080);self.assertEqual(d.name,'ehi_nira_it');self.assertEqual(len(self.created[0].chunks[0]),2560)
 async def test_unsupported_audio_rejected(self):
  await self.h.handle_event(Detect().event());keep=await self.h.handle_event(AudioStart(rate=48000,width=2,channels=1).event());self.assertFalse(keep);self.assertTrue(Error.is_type((await self.event()).type))
if __name__=='__main__':unittest.main()
