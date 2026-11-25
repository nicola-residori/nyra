"""Research candidate: frozen Italian encoder + dedicated Ehi Nira verifier.
Only approved synthetic WAVs. Original splits immutable. Never deploys itself.
"""
from pathlib import Path
import os,sys,json,time,hashlib,fcntl,importlib.util,shutil,gzip,collections
os.environ.update(USE_TF='0',USE_FLAX='0',HF_HUB_DISABLE_TELEMETRY='1')
import numpy as np,torch
from scipy.io.wavfile import read
from transformers import Wav2Vec2ForCTC,Wav2Vec2FeatureExtractor
BASE=Path('/content/nyra_oww_v1/oww-it-v1-001');ROOT=Path('/content/nyra_italian_verifier_v2');ROOT.mkdir(exist_ok=True)
BKP=Path('/content/drive/MyDrive/nyra_openwakeword_it/oww-it-v1-001/italian_verifier_v2');BKP.mkdir(exist_ok=True)
ID='jonatasgrosman/wav2vec2-large-xlsr-53-italian';REV='dab04a3e00d8326052f3fb22a6ff276b822f6131';SEED=918311;SR=16000;N=44800
spec=importlib.util.spec_from_file_location('approved','/content/nyra_oww_worker.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w);old=w.old_worker()
torch.set_num_threads(2);torch.manual_seed(SEED);np.random.seed(SEED)

def save(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.partial');tmp.write_text(json.dumps(obj,indent=2));tmp.replace(path)
def backup(path):
 path=Path(path);dest=BKP/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_suffix('.partial');shutil.copy2(path,tmp);assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(tmp.read_bytes()).digest();tmp.replace(dest)
def progress(stage,**kw):
 obj=dict(stage=stage,updated=time.time(),**kw);save(ROOT/'progress.json',obj);backup(ROOT/'progress.json');print('ITALIAN_VERIFIER',json.dumps(obj),flush=True)
def readwav(row):
 p=BASE/row['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];sr,a=read(p);assert sr==SR and a.dtype==np.int16;return a.astype(np.float32)/32768

def plan_training():
 target=ROOT/'training_plan.json'
 if target.exists():return json.loads(target.read_text())
 rows=json.loads((BASE/'dataset.json').read_text())['rows'];rng=np.random.default_rng(SEED);groups=collections.defaultdict(list)
 for r in rows:
  if r['split']=='training' and r['kind']=='positive' and r['phrase']=='ehi_nira_it':groups[r['family']].append(r)
 plan=[]
 for family,rs in sorted(groups.items()):
  for j in rng.choice(len(rs),min(12,len(rs)),False):
   for aug in range(2):plan.append(dict(row=rs[int(j)],label=1,aug=aug,seed=SEED+rs[int(j)]['id']*23+aug))
 for kind,n in [('hard',1800),('speech',800),('continuous',400),('noise',200),('solo_control',400)]:
  rs=[r for r in rows if r['split']=='training' and (r['kind']==kind if kind!='solo_control' else r['kind']=='positive' and r['phrase']=='nira_it')]
  for j in rng.choice(len(rs),min(n,len(rs)),False):plan.append(dict(row=rs[int(j)],label=0,aug=0,seed=SEED+rs[int(j)]['id']*23))
 for i in range(400):plan.append(dict(row=None,label=0,aug=0,seed=SEED+i*7907,quiet_id=-i-1))
 save(target,plan);backup(target);progress('plan_ready',cases=len(plan),positives=sum(x['label'] for x in plan),training_source_only=True);return plan

def crop(audio,end):
 end=min(len(audio),max(1,round(end*SR)));audio=audio[max(0,end-N):end]
 if len(audio)<N:audio=np.pad(audio,(N-len(audio),0))
 return audio.astype(np.float32)
def training_audio(item):
 rng=np.random.default_rng(item['seed']);row=item['row'];floor=int(rng.choice([-75,-60,-45]));seed=item['seed']
 if row is None:return rng.normal(0,10**(float(rng.uniform(-80,-35))/20),N).astype(np.float32)
 a=readwav(row)
 if item['label']:
  if item['aug']:a=old.acoustic(a,str(rng.choice(old.ACOUSTIC_PROFILES)),seed)
  b=old.continuous_context(a,seed,pre_s=4.,tail_s=1.,floor_dbfs=floor);end=4.+len(a)/SR+float(rng.uniform(-.08,.4));x=crop(b,end)
 else:
  b=old.continuous_context(a,seed,pre_s=4.,tail_s=1.,floor_dbfs=floor)
  if len(a)>N:end=float(rng.uniform(4.+N/SR,4.+len(a)/SR))
  else:end=4.+len(a)/SR+float(rng.uniform(0,.4))
  x=crop(b,end)
 return np.clip(x*32767,-32768,32767).astype(np.int16).astype(np.float32)/32768

_FRONT=None;_FE=None
def init_front():
 global _FRONT,_FE
 if _FRONT is None:
  assert torch.cuda.is_available();_FE=Wav2Vec2FeatureExtractor.from_pretrained(ID,revision=REV);_FRONT=Wav2Vec2ForCTC.from_pretrained(ID,revision=REV,attn_implementation='eager').wav2vec2.to('cuda').eval()
  for p in _FRONT.parameters():p.requires_grad_(False)
 return _FRONT,_FE

def embed(waves):
 front,fe=init_front();assert all(len(a)==N for a in waves)
 inputs=fe(waves,sampling_rate=SR,return_tensors='pt',padding=True)
 with torch.inference_mode():h=front(**{k:v.to('cuda') for k,v in inputs.items()}).last_hidden_state;x=torch.nn.functional.adaptive_avg_pool1d(h.transpose(1,2),32).transpose(1,2).cpu().numpy().astype(np.float16)
 assert x.shape==(len(waves),32,1024) and np.isfinite(x).all();return x

def prepare_training():
 plan=plan_training();folder=ROOT/'training_features';folder.mkdir(exist_ok=True);pending=[];waves=[]
 def flush():
  if not pending:return
  x=embed(waves)
  for idx,a in zip(pending,x):
   p=folder/f'{idx:05}.npy';tmp=p.with_suffix('.partial')
   with tmp.open('wb') as f:np.save(f,a)
   tmp.replace(p)
  pending.clear();waves.clear()
 for i,item in enumerate(plan):
  if not (folder/f'{i:05}.npy').is_file():pending.append(i);waves.append(training_audio(item))
  if len(pending)>=8:flush()
  if (i+1)%128==0:flush();progress('training_features',done=i+1,total=len(plan))
 flush();progress('training_features_complete',total=len(plan))

class Head(torch.nn.Module):
 def __init__(self):
  super().__init__();self.norm=torch.nn.LayerNorm(1024);self.conv=torch.nn.Sequential(torch.nn.Conv1d(1024,64,5,padding=2),torch.nn.GELU(),torch.nn.Dropout(.1),torch.nn.Conv1d(64,64,5,padding=4,dilation=2),torch.nn.GELU(),torch.nn.Conv1d(64,64,3,padding=2,dilation=2),torch.nn.GELU());self.fc=torch.nn.Sequential(torch.nn.Linear(128,64),torch.nn.GELU(),torch.nn.Dropout(.1),torch.nn.Linear(64,1))
 def forward(self,x):
  x=self.conv(self.norm(x).transpose(1,2));x=torch.cat([x.mean(-1),x.amax(-1)],dim=1);return self.fc(x).squeeze(-1)

def train():
 plan=plan_training();X=torch.from_numpy(np.stack([np.load(ROOT/'training_features'/f'{i:05}.npy') for i in range(len(plan))])).to('cuda',dtype=torch.float32);y=torch.tensor([r['label'] for r in plan],dtype=torch.float32,device='cuda')
 ids=np.array([r['row']['id'] if r['row'] else r['quiet_id'] for r in plan]);internal=ids%10==0;pos=np.flatnonzero((~internal)&(y.cpu().numpy()==1));neg=np.flatnonzero((~internal)&(y.cpu().numpy()==0));vi=torch.from_numpy(np.flatnonzero(internal)).to('cuda');m=Head().to('cuda');opt=torch.optim.AdamW(m.parameters(),lr=3e-4,weight_decay=.01);step0=0;best=1e9
 checkpoint=ROOT/'checkpoint.pt'
 if checkpoint.exists():
  c=torch.load(checkpoint,map_location='cuda',weights_only=True);m.load_state_dict(c['model']);opt.load_state_dict(c['optimizer']);step0=c['step'];best=c['best']
 for step in range(step0,1200):
  rng=np.random.default_rng(SEED+step);idx=np.r_[rng.choice(pos,64),rng.choice(neg,64)];m.train();opt.zero_grad();batch=X[idx];shift=int(rng.integers(-4,5));batch=torch.roll(batch,shift,1);batch[:, :shift if shift>0 else 0]=X[idx,:1] if shift>0 else batch[:,:0];
  if shift<0:batch[:,shift:]=X[idx,-1:]
  loss=torch.nn.functional.binary_cross_entropy_with_logits(m(batch),y[idx]);loss.backward();opt.step()
  if (step+1)%100==0:
   m.eval()
   with torch.inference_mode():val=float(torch.nn.functional.binary_cross_entropy_with_logits(m(X[vi]),y[vi]))
   if val<best:best=val;torch.save(m.state_dict(),ROOT/'best.pt');backup(ROOT/'best.pt')
   torch.save(dict(model=m.state_dict(),optimizer=opt.state_dict(),step=step+1,best=best),checkpoint);backup(checkpoint);progress('train',step=step+1,total=1200,loss=float(loss),internal_validation_loss=val,best_loss=best)
 save(ROOT/'trained.json',dict(steps=1200,best_loss=best,feature_shape=[32,1024],foundation=ID,revision=REV,internal_split='original training source id modulo 10; repeated augmentation grouped'));backup(ROOT/'trained.json');progress('trained')

def eval_audio(item):
 row=item['row'];a=readwav(row);seed=18473+row['id']*7919
 if row['kind']=='positive':
  profile,db=item['condition'].rsplit('__floor',1);i=old.ACOUSTIC_PROFILES.index(profile);j=(-75,-60,-45).index(int(db));b=old.continuous_context(old.acoustic(a,profile,seed+i*1301),seed+i*7919+j,floor_dbfs=int(db))
 else:b=old.continuous_context(a,seed)
 return np.clip(b*32767,-32768,32767).astype(np.int16).astype(np.float32)/32768

def validate():
 m=Head().to('cuda').eval();m.load_state_dict(torch.load(ROOT/'best.pt',map_location='cuda',weights_only=True));plan=json.loads((BASE/'stream_v3/plan.json').read_text());lookup={(x['row']['id'],x['condition']):x for x in plan if x['split']=='validation'}
 with gzip.open('/content/nyra_recovery/validation_scores.json.gz','rt') as f:rows=json.load(f)
 output=ROOT/'validation.json';results=json.loads(output.read_text()) if output.exists() else [];done={(r['id'],r['condition']) for r in results}
 for index,r in enumerate(rows):
  if (r['id'],r['condition']) in done:continue
  x=np.asarray(r['probs']['ehi_nira_it']);t=np.asarray(r['times']);x=np.min(np.lib.stride_tricks.sliding_window_view(x,3),axis=1);t=t[2:];events=[]
  for ti in t[x>.6]:
   if not events or ti-events[-1]>=2:events.append(float(ti))
  ev=[]
  if events:
   audio=eval_audio(lookup[(r['id'],r['condition'])]);features=embed([crop(audio,ti+.24) for ti in events])
   with torch.inference_mode():scores=m(torch.from_numpy(features).to('cuda',dtype=torch.float32)).sigmoid().cpu().tolist()
   ev=[dict(t=ti+.24,p=p) for ti,p in zip(events,scores)]
  results.append({**{k:r[k] for k in ['id','kind','phrase','condition','variant','family','duration','start','end']},'events':ev})
  if (index+1)%50==0:save(output,results);backup(output);progress('validation',done=index+1,total=len(rows))
 save(output,results);backup(output);grid=[]
 for cut in [.01,.02,.05,.1,.15,.2,.3,.4,.5,.6,.7,.8,.9,.95,.99]:
  hit=total=ambient=hard=hardtotal=preword=control=0;hours=0;conditions=collections.defaultdict(lambda:[0,0]);variants=collections.defaultdict(lambda:[0,0]);voices=collections.defaultdict(lambda:[0,0])
  for r in results:
   times=[e['t'] for e in r['events'] if e['p']>=cut]
   if r['kind']=='positive' and r['phrase']=='ehi_nira_it':
    ok=any(r['start']<=t<=r['end']+1 for t in times);hit+=ok;total+=1;preword+=any(t<r['start'] for t in times)
    for group,key in [(conditions,r['condition']),(variants,r['variant']),(voices,r['family'].split('-')[0])]:group[key][0]+=ok;group[key][1]+=1
   elif r['kind']=='positive':control+=bool(times)
   elif r['kind']=='ambient':ambient+=len(times);hours+=r['duration']/3600
   elif r['kind']=='hard':hard+=bool(times);hardtotal+=1
  grid.append(dict(cutoff=cut,hits=hit,total=total,recall=hit/total,faph=ambient/hours,ambient_events=ambient,ambient_hours=hours,hard_false_clips=hard,hard_total=hardtotal,preword=preword,solo_control_triggers=control,min_condition=min(a/b for a,b in conditions.values()),min_variant=min(a/b for a,b in variants.values()),min_voice=min(a/b for a,b in voices.values())))
 good=[g for g in grid if g['recall']>=.99 and g['min_condition']>=.9 and g['min_variant']>=.95 and g['min_voice']>=.95 and g['faph']<=2 and g['hard_false_clips']/g['hard_total']<=.05 and g['preword']==0]
 report=dict(selected=min(good,key=lambda r:(r['faph'],r['hard_false_clips'])) if good else None,grid=grid,all_audio_synthetic=True,human_test=False,heldout_test=False)
 save(ROOT/'calibration.json',report);backup(ROOT/'calibration.json');progress('validation_complete',**report)

if __name__=='__main__':
 with (ROOT/'controller.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for phase in sys.argv[1:] or ['prepare_training','train','validate']:
   progress('starting',phase=phase);globals()[phase]()
