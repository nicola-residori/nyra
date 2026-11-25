"""Evaluate frozen exported candidate on original synthetic streams, resumably."""
from pathlib import Path
import argparse,json,hashlib,importlib.util,time,fcntl,collections,os
import numpy as np
from scipy.io.wavfile import read
from candidate_engine import CandidateEngine

def render(item,root,old):
 r=item['row'];p=root/r['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 sr,a=read(p);assert sr==16000 and a.dtype==np.int16
 a=a.astype(np.float32)/32768;seed=18473+r['id']*7919
 if r['kind']=='positive':
  profile,db=item['condition'].rsplit('__floor',1);i=old.ACOUSTIC_PROFILES.index(profile);j=(-75,-60,-45).index(int(db))
  b=old.continuous_context(old.acoustic(a,profile,seed+i*1301),seed+i*7919+j,floor_dbfs=int(db))
 else:b=old.continuous_context(a,seed)
 return np.clip(b*32767,-32768,32767).astype('<i2')

def report(rows):
 out={}
 for split in ('validation','testing'):
  rr=[r for r in rows if r['split']==split];positive=[r for r in rr if r['kind']=='positive' and r['phrase']=='ehi_nira_it'];ambient=[r for r in rr if r['kind']=='ambient'];hard=[r for r in rr if r['kind']=='hard'];speech=[r for r in rr if r['kind']=='speech'];solo=[r for r in rr if r['kind']=='positive' and r['phrase']=='nira_it']
  def hits(a):return sum(bool(r['hit']) for r in a)
  def groups(field):
   g=collections.defaultdict(lambda:[0,0])
   for r in positive:g[r[field]][0]+=r['hit'];g[r[field]][1]+=1
   return dict(g)
  hours=sum(r['duration'] for r in ambient)/3600;events=sum(len(r['detections']) for r in ambient)
  out[split]=dict(completed=len(rr),positive_hits=hits(positive),positive_total=len(positive),recall=hits(positive)/len(positive) if positive else None,ambient_events=events,ambient_hours=hours,faph=events/hours if hours else None,hard_hits=hits(hard),hard_total=len(hard),speech_hits=hits(speech),speech_total=len(speech),solo_nira_hits=sum(bool(r['detections']) for r in solo),solo_nira_total=len(solo),preword=sum(any(e['t']<4 for e in r['detections']) for r in positive),by_variant=groups('variant'),by_condition=groups('condition'),by_voice=groups('voice'))
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 lock=open(a.output/'run.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 configsha=hashlib.sha256((a.candidate/'config.json').read_bytes()).hexdigest();manifest=json.loads((a.candidate/'manifest.json').read_text());print('MANIFEST_FILES',len(manifest),flush=True)
 for name,sha in manifest.items():assert hashlib.sha256((a.candidate/name).read_bytes()).hexdigest()==sha,(name,'hash mismatch')
 spec=importlib.util.spec_from_file_location('approved_original',a.data/'original_worker.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 plan=json.loads((a.data/'plan.json').read_text());results=a.output/'results.jsonl';rows=[]
 if results.exists():
  for line in results.read_text().splitlines():rows.append(json.loads(line))
 assert all(r['config_sha256']==configsha for r in rows),'Configuration changed; separate output required'
 done={r['key'] for r in rows};engine=CandidateEngine(a.candidate);start=time.monotonic()
 for i,item in enumerate(plan):
  key=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
  if key in done:continue
  if a.limit is not None and len(rows)>=a.limit:break
  pcm=render(item,a.data,old);engine.reset();tic=time.monotonic()
  for off in range(0,len(pcm),1280):
   chunk=pcm[off:off+1280]
   if len(chunk)<1280:chunk=np.pad(chunk,(0,1280-len(chunk)))
   engine.feed(chunk.tobytes())
  r=item['row'];positive=r['kind']=='positive';hit=any(4<=e['t']<=4+r['duration']+1 for e in engine.detections) if positive else bool(engine.detections)
  record=dict(key=key,config_sha256=configsha,split=item['split'],id=r['id'],kind=r['kind'],phrase=r.get('phrase'),variant=r.get('variant','negative'),voice=r.get('family','unknown').split('-')[0],condition=item['condition'],duration=len(pcm)/16000,hit=bool(hit),candidates=engine.candidates,detections=engine.detections,wall_seconds=time.monotonic()-tic)
  with results.open('a') as f:f.write(json.dumps(record)+'\n');f.flush();os.fsync(f.fileno())
  rows.append(record);done.add(key)
  if len(rows)%20==0 or len(rows)==1:
   summary=report(rows);tmp=a.output/'progress.partial';tmp.write_text(json.dumps(dict(completed=len(rows),total=len(plan),elapsed_this_run=time.monotonic()-start,metrics=summary),indent=2));tmp.replace(a.output/'progress.json');print('PROGRESS',len(rows),len(plan),round(time.monotonic()-start,1),flush=True)
 (a.output/'report.json').write_text(json.dumps(report(rows),indent=2));print('EVALUATION_COMPLETE',len(rows),len(plan),flush=True)
if __name__=='__main__':main()
