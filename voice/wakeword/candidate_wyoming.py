"""Wyoming transport for the frozen research candidate. No PCM is persisted."""
import asyncio,argparse,logging,json,signal
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from collections import deque
from wyoming.audio import AudioStart,AudioChunk,AudioStop
from wyoming.info import Describe,Info,WakeProgram,WakeModel,Attribution
from wyoming.wake import Detect,Detection,NotDetected
from wyoming.error import Error
from wyoming.server import AsyncEventHandler,AsyncServer
NAME='ehi_nira_it'
# Bound CPU load and avoid simultaneous large verifier work from two speakers.
EXECUTOR=ThreadPoolExecutor(max_workers=1,thread_name_prefix='nyra-inference')
def info():
 a=Attribution(name='Nyra research candidate',url='https://github.com/rhasspy/pyopen-wakeword')
 return Info(wake=[WakeProgram(name='Nyra Italian candidate',attribution=a,installed=True,description='Experimental Ehi Nira server recognizer',version='italian-v2-int8-1',models=[WakeModel(name=NAME,attribution=a,installed=True,description='Ehi Nira',version='1',languages=['it'],phrase='Ehi Nira')])])
def diagnostic_snapshot(engines):
 fields=('t','candidate_t','primary_probability','probability','vad_speech_seconds','verifier_wall_seconds','phrase_cost','prior_speech_frames')
 def scalar_rows(rows):return [{k:r[k] for k in fields if k in r and isinstance(r[k],(int,float,type(None)))} for r in rows[-12:]]
 return [dict(engine=i,audio_seconds_processed=e.samples/16000,candidates=scalar_rows(e.candidates),detections=scalar_rows(e.detections)) for i,e in enumerate(engines)]
class ReadyEngines:
 def __init__(self,engines):self.ready=deque(engines);self.leased=set()
 def acquire(self):
  if not self.ready:raise RuntimeError('Both speaker streams are already active')
  engine=self.ready.popleft();self.leased.add(id(engine));return engine
 def release(self,engine):
  if id(engine) in self.leased:
   self.leased.remove(id(engine));engine.reset();self.ready.append(engine)
class CandidateHandler(AsyncEventHandler):
 def __init__(self,reader,writer,factory,release=None):
  super().__init__(reader,writer);self.factory=factory;self.release=release;self.engine=None;self.active=False;self.started=False;self.buffer=bytearray();self.origin=None
 async def work(self,fn,*args):return await asyncio.get_running_loop().run_in_executor(EXECUTOR,fn,*args)
 async def handle_event(self,event):
  if Describe.is_type(event.type):await self.write_event(info().event());return True
  if Detect.is_type(event.type):
   names=Detect.from_event(event).names
   if names and NAME not in names:await self.write_event(Error(text='Unsupported wake word',code='unsupported-wake-word').event());return False
   if self.engine is None:
    try:self.engine=await self.work(self.factory)
    except RuntimeError as error:
     await self.write_event(Error(text=str(error),code='busy').event());return False
   else:await self.work(self.engine.reset)
   self.buffer.clear();self.origin=None;self.active=True;self.started=False;return True
  if AudioStart.is_type(event.type):
   a=AudioStart.from_event(event)
   if (a.rate,a.width,a.channels)!=(16000,2,1):await self.write_event(Error(text='Expected 16kHz PCM16 mono',code='unsupported-audio').event());return False
   self.started=True;return True
  if AudioChunk.is_type(event.type) and self.active:
   a=AudioChunk.from_event(event)
   if not self.started or (a.rate,a.width,a.channels)!=(16000,2,1):await self.write_event(Error(text='Invalid audio stream',code='unsupported-audio').event());return False
   if self.origin is None:self.origin=a.timestamp or 0
   self.buffer.extend(a.audio)
   while len(self.buffer)>=2560:
    b=bytes(self.buffer[:2560]);del self.buffer[:2560];detections=await self.work(self.engine.feed,b)
    if detections:
     d=detections[0];stamp=self.origin+round(d['candidate_t']*1000)
     logging.info('WAKE_DETECTED timestamp_ms=%s probability=%.4f',stamp,d['probability'])
     await self.write_event(Detection(name=NAME,timestamp=stamp).event());self.active=False;self.buffer.clear();return True
   return True
  if AudioStop.is_type(event.type) and self.active:await self.write_event(NotDetected().event());self.active=False
  return True
 async def disconnect(self):
  self.buffer.clear();engine=self.engine;self.engine=None
  if engine is not None and self.release is not None:await self.work(self.release,engine)
async def main():
 logging.basicConfig(level=logging.INFO)
 p=argparse.ArgumentParser();p.add_argument('--uri',default='tcp://127.0.0.1:10401');p.add_argument('--candidate',type=Path,required=True);a=p.parse_args()
 from candidate_engine import CandidateEngine
 # Reuse the large immutable ONNX session; keep streaming state per client.
 shared=CandidateEngine(a.candidate,history_limit=64)
 second=CandidateEngine(a.candidate,skip_verifier=True,history_limit=64);second.session=shared.session
 pool=ReadyEngines([shared,second])
 # On-demand scalar diagnostics, never PCM or transcripts, without restarting.
 asyncio.get_running_loop().add_signal_handler(signal.SIGUSR1,lambda:logging.info('SCORE_SNAPSHOT %s',json.dumps(diagnostic_snapshot([shared,second]))))
 server=AsyncServer.from_uri(a.uri);logging.warning('Experimental Nyra provider listening: %s',a.uri)
 await server.run(partial(CandidateHandler,factory=pool.acquire,release=pool.release))
if __name__=='__main__':asyncio.run(main())
