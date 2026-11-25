from pathlib import Path
import json,hashlib,urllib.request,importlib.util,collections,time
import numpy as np,onnxruntime as ort
ROOT=Path('/content/nyra_italian_vad');ROOT.mkdir(exist_ok=True);REV='bfa5f8cef40abb5de2bd4a2f4c3f22778172dfec'
p=ROOT/'silero_vad.onnx'
if not p.exists():urllib.request.urlretrieve(f'https://raw.githubusercontent.com/snakers4/silero-vad/{REV}/src/silero_vad/data/silero_vad.onnx',p)
spec=importlib.util.spec_from_file_location('v','/content/italian_verifier_v3.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1;sess=ort.InferenceSession(str(p),opts,providers=['CPUExecutionProvider']);print('VAD_MODEL',REV,hashlib.sha256(p.read_bytes()).hexdigest(),[(x.name,x.shape) for x in sess.get_inputs()],flush=True)
def vad(a):
 state=np.zeros((2,1,128),np.float32);context=np.zeros((1,64),np.float32);ps=[]
 for offset in range(0,len(a),512):
  chunk=a[offset:offset+512]
  if len(chunk)<512:chunk=np.pad(chunk,(0,512-len(chunk)))
  x=np.concatenate([context,chunk[None,:]],axis=1).astype(np.float32);out,state=sess.run(None,{'input':x,'state':state,'sr':np.array(16000,np.int64)});context=x[:,-64:];ps.append(float(out[0,0]))
 return ps
plan=json.loads((v.BASE/'stream_v3/plan.json').read_text());lookup={(x['row']['id'],x['condition']):x for x in plan if x['split']=='validation'}
rows=json.loads(Path('/content/nyra_italian_verifier_v2/validation_relaxed.json').read_text());other={(r['id'],r['condition']):r for r in json.loads(Path('/content/nyra_italian_verifier_v3/validation_relaxed.json').read_text())}
cache=ROOT/'validation.json';results=json.loads(cache.read_text()) if cache.exists() else [];done={(r['id'],r['condition']) for r in results};start=time.monotonic()
for i,r in enumerate(rows):
 key=(r['id'],r['condition'])
 if key in done:continue
 ev=[]
 if r['events']:
  a=v.eval_audio(lookup[key]);o=other[key];assert [e['t'] for e in r['events']]==[e['t'] for e in o['events']]
  for e,e3 in zip(r['events'],o['events']):ev.append(dict(t=e['t'],v2=e['p'],v3=e3['p'],vad=vad(v.crop(a,e['t']))))
 results.append({**r,'events':ev})
 if (i+1)%100==0:v.save(cache,results);print('ITALIAN_VAD_PROGRESS',i+1,len(rows),round(time.monotonic()-start,1),flush=True)
v.save(cache,results);v.backup(ROOT/'progress.json') if False else None
grid=[]
for model in ['v2','v3']:
 for cut in [.005,.01,.015,.02,.03,.04,.05,.075,.1,.15,.2]:
  for voice_cut in [.1,.3,.5]:
   hit=total=ambient=hard=hardtotal=preword=control=0;hours=0.;conditions=collections.defaultdict(lambda:[0,0]);variants=collections.defaultdict(lambda:[0,0]);voices=collections.defaultdict(lambda:[0,0])
   for r in results:
    times=[e['t'] for e in r['events'] if e[model]>=cut and sum(p>=voice_cut for p in e['vad'])*.032>=.096]
    if r['kind']=='positive' and r['phrase']=='ehi_nira_it':
     ok=any(r['start']<=t<=r['end']+1 for t in times);hit+=ok;total+=1;preword+=any(t<r['start'] for t in times)
     for group,key in [(conditions,r['condition']),(variants,r['variant']),(voices,r['family'].split('-')[0])]:group[key][0]+=ok;group[key][1]+=1
    elif r['kind']=='positive':control+=bool(times)
    elif r['kind']=='ambient':ambient+=len(times);hours+=r['duration']/3600
    elif r['kind']=='hard':hard+=bool(times);hardtotal+=1
   grid.append(dict(model=model,cutoff=cut,vad_cutoff=voice_cut,hits=hit,total=total,recall=hit/total,faph=ambient/hours,ambient_events=ambient,ambient_hours=hours,hard_false_clips=hard,hard_total=hardtotal,preword=preword,solo_control_triggers=control,min_condition=min(a/b for a,b in conditions.values()),min_variant=min(a/b for a,b in variants.values()),min_voice=min(a/b for a,b in voices.values())))
good=[g for g in grid if g['recall']>=.99 and g['min_condition']>=.9 and g['min_variant']>=.95 and g['min_voice']>=.95 and g['faph']<=2 and g['hard_false_clips']/g['hard_total']<=.05 and g['preword']==0]
report=dict(selected=min(good,key=lambda r:(r['faph'],r['hard_false_clips'],-r['recall'])) if good else None,grid=grid,vad_revision=REV,vad_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
v.save(ROOT/'report.json',report);dest=v.BKP.parent/'italian_vad';shutil=None
import shutil
shutil.copytree(ROOT,dest,dirs_exist_ok=True)
print('ITALIAN_VAD_COMPLETE',json.dumps(report),flush=True)
