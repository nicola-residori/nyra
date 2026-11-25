"""Exact reuse of the pinned frontend's deterministic initial zero history."""
import numpy as np
from pyopen_wakeword import OpenWakeWordFeatures
class CachedStreamFront:
 def __init__(self):
  self.front=OpenWakeWordFeatures.from_builtin()
  assert self.front.new_audio_samples==128000,'Pinned frontend startup policy changed'
  self.front.new_audio_samples-=1280
  self.prefix=[x.copy() for x in self.front.process_streaming(bytes(2560))]
  assert self.front.new_audio_samples==1280
  self.audio=self.front.audio.copy();self.mels=self.front.mels.copy();self.na=self.front.new_audio_samples;self.nm=self.front.new_mels
  self.reset()
 def reset(self):
  self.front.audio[:]=self.audio;self.front.mels[:]=self.mels;self.front.new_audio_samples=self.na;self.front.new_mels=self.nm;self.pending=True
 def process_streaming(self,audio_chunk):
  if self.pending:
   self.pending=False
   yield from self.prefix
  yield from self.front.process_streaming(audio_chunk)
def regression():
 import time
 raw=OpenWakeWordFeatures.from_builtin();cached=CachedStreamFront();rng=np.random.default_rng(6713);start=time.monotonic()
 for n,chunk in ((51200,1280),(4771,1280),(12000,160),(51200,480)):
  audio=rng.integers(-8000,8000,n,dtype=np.int16);outputs=[]
  for f in (raw,cached):
   f.reset();out=[]
   for i in range(0,n,chunk):
    a=audio[i:i+chunk]
    if len(a)<chunk:a=np.pad(a,(0,chunk-len(a)))
    out.extend(x[0,0].copy() for x in f.process_streaming(a.astype('<i2').tobytes()))
   outputs.append(np.concatenate(out))
  assert outputs[0].shape==outputs[1].shape,(n,chunk,[x.shape for x in outputs])
  assert np.array_equal(*outputs),(n,chunk,float(np.max(np.abs(outputs[0]-outputs[1]))))
  print('FRONT_CACHE_BIT_EXACT',n,chunk,outputs[0].shape,flush=True)
 print('FRONT_CACHE_REGRESSION_PASSED',round(time.monotonic()-start,3),flush=True)
if __name__=='__main__':regression()
