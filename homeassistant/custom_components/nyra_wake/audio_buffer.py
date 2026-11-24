"""Bounded PCM16 mono 16kHz buffer; no filesystem access."""
from collections import deque
class AudioBuffer:
 def __init__(self,seconds=4):self.capacity=round(seconds*32000);self.clear()
 def clear(self):self.chunks=deque();self.byte_count=0
 def append(self,audio,timestamp):
  assert len(audio)%2==0
  self.chunks.append((audio,timestamp));self.byte_count+=len(audio)
  while self.chunks and self.byte_count>self.capacity:
   data,ts=self.chunks.popleft();self.byte_count-=len(data)
 def after(self,timestamp):
  output=[]
  for data,ts in self.chunks:
   if ts+len(data)/32<=timestamp:continue
   skip=max(0,round((timestamp-ts)*16)*2)
   if skip<len(data):output.append((data[skip:],ts+skip/32))
  return output
