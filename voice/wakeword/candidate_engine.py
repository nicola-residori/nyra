"""Frozen streaming research candidate; audio stays in RAM, no recordings."""
from pathlib import Path
from collections import deque
import json,time,hashlib
import numpy as np,onnxruntime as ort
from pyopen_wakeword import OpenWakeWord
from cached_frontend import CachedStreamFront

class VoiceGate:
 def __init__(self,path):
  opt=ort.SessionOptions();opt.intra_op_num_threads=1;opt.inter_op_num_threads=1;self.session=ort.InferenceSession(str(path),opt,providers=['CPUExecutionProvider'])
 def probabilities(self,audio):
  state=np.zeros((2,1,128),np.float32);context=np.zeros((1,64),np.float32);probs=[]
  for offset in range(0,len(audio),512):
   chunk=audio[offset:offset+512]
   if len(chunk)<512:chunk=np.pad(chunk,(0,512-len(chunk)))
   x=np.concatenate([context,chunk[None,:]],axis=1).astype(np.float32);p,state=self.session.run(None,{'input':x,'state':state,'sr':np.array(16000,np.int64)});context=x[:,-64:];probs.append(float(p[0,0]))
  return probs

class CandidateEngine:
 def __init__(self,directory,threads=2,skip_verifier=False,history_limit=None):
  self.history_limit=history_limit
  self.directory=Path(directory);self.config=json.loads((self.directory/'config.json').read_text());self.front=CachedStreamFront();self.primary=OpenWakeWord.from_model(self.directory/'primary_ehi_nira.tflite');self.vad=VoiceGate(self.directory/'silero_vad.onnx');self.session=None
  if not skip_verifier:
   opt=ort.SessionOptions();opt.intra_op_num_threads=threads;opt.inter_op_num_threads=1;self.session=ort.InferenceSession(str(self.directory/'verifier.int8.onnx'),opt,providers=['CPUExecutionProvider'])
  self.reset()
 def reset(self):
  self.front.reset();self.primary.reset();self.samples=0;self.ring=bytearray();self.consecutive=0;self.last_candidate=-1e9;self.pending=deque();self.candidates=[];self.detections=[]
 def feed(self,pcm):
  assert len(pcm)==2560,'Feed exactly 80ms of 16kHz mono PCM16'
  self.samples+=1280;now=self.samples/16000;self.ring.extend(pcm);capacity=51200*2
  if len(self.ring)>capacity:del self.ring[:-capacity]
  for emb in self.front.process_streaming(pcm):
   for p in self.primary.process_streaming(emb):
    self.consecutive=self.consecutive+1 if float(p)>self.config['primary_cutoff'] else 0
    if self.consecutive>=self.config['primary_consecutive_frames'] and now-self.last_candidate>=self.config['refractory_seconds']:
     self.last_candidate=now;entry=dict(t=now,primary_probability=float(p));self.pending.append((now,now+self.config['verifier_post_trigger_seconds'],entry));self.candidates.append(entry)
     if self.history_limit and len(self.candidates)>self.history_limit:del self.candidates[:-self.history_limit]
  emitted=[]
  while self.pending and self.pending[0][1]<=now+1e-7:
   candidate,deadline,entry=self.pending.popleft();all_audio=np.frombuffer(self.ring,dtype='<i2').astype(np.float32)/32768;end=len(all_audio)-round((now-deadline)*16000);audio=all_audio[max(0,end-self.config['verifier_window_samples']):end]
   if len(audio)<self.config['verifier_window_samples']:audio=np.pad(audio,(self.config['verifier_window_samples']-len(audio),0))
   assert len(audio)==44800;probs=self.vad.probabilities(audio);speech=sum(p>=self.config['vad_cutoff'] for p in probs)*.032;started=time.monotonic();probability=None
   if speech>=self.config['vad_min_speech_seconds'] and self.session is not None:probability=float(self.session.run(None,{'audio':audio[None].astype(np.float32)})[0][0])
   record=dict(candidate_t=candidate,t=deadline,probability=probability,vad_speech_seconds=speech,verifier_wall_seconds=time.monotonic()-started);entry.update(record)
   if probability is not None and probability>=self.config['verifier_cutoff']:
    self.detections.append(record);emitted.append(record)
    if self.history_limit and len(self.detections)>self.history_limit:del self.detections[:-self.history_limit]
  return emitted
