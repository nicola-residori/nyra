"""Nyra openWakeWord prototype: immutable V6 synthetic audio, frozen OWW frontend.
The new Keras head follows OWW's DNN/LayerNorm topology; it is not the microWakeWord trainer.
No real-room accuracy claims are inferred from synthetic evaluation.
"""
from pathlib import Path
import os,sys,json,hashlib,shutil,tarfile,collections,fcntl,time,importlib.util,argparse,gc
ROOT=Path('/content/nyra_oww_v1/oww-it-v1-001')
SOURCE=Path('/content/drive/MyDrive/wakeword_training_nyra_it_v4/nyra-it-v6-004-continuous')
BACKUP=Path('/content/drive/MyDrive/nyra_openwakeword_it/oww-it-v1-001')
OWW=Path('/content/nyra_oww_source');PYOWW=Path('/content/nyra_pyoww_source')
PHRASES=('ehi_nira_it','nira_it');SEED=18473;FRONTEND_VERSION='oww-frozen-v2-exact-length'
ROOT.mkdir(parents=True,exist_ok=True);BACKUP.mkdir(parents=True,exist_ok=True)
def save(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.partial');tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False));tmp.replace(p)
def load(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def guard(gib=8):
 assert shutil.disk_usage(ROOT).free>=gib*2**30,'Insufficient local disk: preserve existing files and stop'
def progress(stage,**kw):
 x=dict(stage=stage,updated=time.time(),**kw);save(ROOT/'progress.json',x);save(BACKUP/'progress.json',x);print(json.dumps(x),flush=True)
def old_worker():
 p=SOURCE.parent/'recovery_snapshots'/SOURCE.name/'nyra_v6_worker.py'
 spec=importlib.util.spec_from_file_location('approved_v6',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def extract():
 archive=SOURCE/'recovery_dataset_v1.tar.gz';assert archive.stat().st_size==2533330118
 if not (ROOT/'extraction_complete.json').exists():
  guard(25)
  with tarfile.open(archive) as t:
   for m in t.getmembers():
    parts=Path(m.name).parts
    assert parts and parts[0] in ('audio','dataset.json') and '..' not in parts and not m.issym() and not m.islnk(),m.name
   for m in t.getmembers():
    if not (ROOT/m.name).exists():t.extract(m,ROOT,filter='data')
 d=load(ROOT/'dataset.json');assert len({r['id'] for r in d['rows']})==len(d['rows'])
 assert all((ROOT/r['path']).is_file() for r in d['rows'])
 save(ROOT/'extraction_complete.json',dict(rows=len(d['rows']),dataset_sha256=sha(ROOT/'dataset.json')))
 save(BACKUP/'source_provenance.json',dict(source=str(SOURCE),archive_bytes=archive.stat().st_size,dataset_sha256=sha(ROOT/'dataset.json'),all_audio_synthetic=True,source_splits_preserved=True,feature_policy=FRONTEND_VERSION,oww_commit=os.popen(f'git -C {OWW} rev-parse HEAD').read().strip(),pyoww_commit=os.popen(f'git -C {PYOWW} rev-parse HEAD').read().strip(),limitations=['Frozen speech embedding is primarily English-pretrained; Italian generalization requires physical tests.','Validation/test share synthetic voice identities with training; not a human-speaker generalization test.']))
 progress('extract_complete',rows=len(d['rows']))
def features():
 import numpy as np
 from scipy.io.wavfile import read
 import onnxruntime as ort
 ort.preload_dlls()
 from openwakeword.utils import AudioFeatures
 old=old_worker();F=AudioFeatures(device='gpu',ncpu=2)
 assert F.onnx_execution_provider=='CUDAExecutionProvider',F.onnx_execution_provider
 rows=load(ROOT/'dataset.json')['rows'];manifest=[];pending=[];count=0
 def flush():
  nonlocal pending,count
  if not pending:return
  # Batch only exactly equal lengths: no padded tails in scoring or training.
  assert len({len(a) for a,_ in pending})==1
  audio=np.stack([a for a,_ in pending])
  emb=F.embed_clips(audio,batch_size=min(64,len(audio)),ncpu=2)
  for i,(_,meta) in enumerate(pending):
   valid_mels=round(meta['duration']*16000)//160-3
   valid_embeddings=(valid_mels-76)//8+1
   x=emb[i][:valid_embeddings].astype(np.float32);assert x.ndim==2 and x.shape[1]==96 and len(x)>=16 and np.isfinite(x).all(),x.shape
   if meta['split']=='training':x=x[-16:]
   dst=ROOT/meta['feature'];dst.parent.mkdir(parents=True,exist_ok=True);np.save(dst,x)
   count+=1
  pending=[]
 def add(a,meta):
  manifest.append(meta)
  if (ROOT/meta['feature']).exists():return
  # Official batch helper uses ceil for mel allocation, while the model uses floor.
  # Pad universally to a 10 ms boundary, then retain only original complete frames.
  if len(a)%160:a=np.pad(a,(0,160-len(a)%160))
  if pending and len(pending[0][0])!=len(a):flush()
  pending.append((a,meta))
  if len(pending)>=32 or sum(len(x) for x,_ in pending)>32*128000:flush()
 for ri,r in enumerate(rows):
  sr,a=read(ROOT/r['path']);assert sr==16000 and a.dtype==np.int16
  assert sha(ROOT/r['path'])==r['sha256'],'WAV hash mismatch: '+r['path']
  seed=SEED+r['id']*7919;rng=np.random.default_rng(seed)
  base=dict(source_id=r['id'],kind=r['kind'],phrase=r['phrase'],split=r['split'],family=r['family'],variant=r.get('variant','unknown'),utterance_duration=r['duration'])
  if r['split']=='training':
   b=a.astype(np.float32)/32768
   if r['kind']!='noise':b=old.acoustic(b,rng.choice(old.ACOUSTIC_PROFILES),seed)
   b=b*10**float(rng.uniform(-18,0)/20)
   n=51200
   if len(b)>n:
    start=int(rng.integers(0,len(b)-n+1));b=b[start:start+n]
   tail=float(rng.uniform(.02,.25)) if len(b)<n-4000 else 0.
   lead=max(0,(n-len(b))/16000-tail)
   b=old.continuous_context(b,seed,pre_s=lead,tail_s=tail)
   if len(b)<n:b=np.pad(b,(0,n-len(b)))
   meta=dict(base,condition='training',duration=3.2,start=0.,end=3.2,feature=f'features/training/{r["id"]}.npy')
   add(np.clip(b[:n]*32767,-32768,32767).astype(np.int16),meta)
  else:
   for condition,b in old.evaluation_variants(a,r['kind'],seed):
    meta=dict(base,condition=condition,duration=len(b)/16000,start=4.,end=4.+r['duration'],feature=f'features/{r["split"]}/{r["id"]}_{condition}.npy')
    add(np.clip(b*32767,-32768,32767).astype(np.int16),meta)
  if ri%100==0:
   flush();guard();progress('features',source_rows_done=ri,total_source_rows=len(rows),new_feature_files=count)
 flush();save(ROOT/'features.json',dict(policy=FRONTEND_VERSION,dataset_sha256=sha(ROOT/'dataset.json'),rows=manifest));save(BACKUP/'features_manifest.json',dict(policy=FRONTEND_VERSION,rows=len(manifest),dataset_sha256=sha(ROOT/'dataset.json')));progress('features_complete',cases=len(manifest))
def tf_init():
 import tensorflow as tf
 tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.threading.set_inter_op_parallelism_threads(2)
 for g in tf.config.list_physical_devices('GPU'):tf.config.experimental.set_memory_growth(g,True)
 tf.keras.utils.set_random_seed(SEED);return tf
def train():
 import numpy as np
 tf=tf_init();rows=load(ROOT/'features.json')['rows']
 for phrase in PHRASES:
  modeldir=ROOT/'models'/phrase;modeldir.mkdir(parents=True,exist_ok=True);backup=BACKUP/'models'/phrase;backup.mkdir(parents=True,exist_ok=True)
  for name in ('checkpoint.keras','state.json','best.keras','complete.json'):
   if not (modeldir/name).exists() and (backup/name).exists():shutil.copy2(backup/name,modeldir/name)
  if (modeldir/'complete.json').exists():
   assert (modeldir/'best.keras').exists()
   continue
  selected=[r for r in rows if r['split']=='training' and (r['kind']!='positive' or r['phrase']==phrase)]
  X=np.stack([np.load(ROOT/r['feature']) for r in selected]);y=np.array([r['kind']=='positive' for r in selected],np.float32)
  pos=np.flatnonzero(y==1);neg=np.flatnonzero(y==0)
  vr=[r for r in rows if r['split']=='validation' and r['kind']!='ambient' and (r['kind']!='positive' or r['phrase']==phrase)]
  rng=np.random.default_rng(SEED);chosen=[];vx=[];vy=[]
  for positive in (True,False):
   candidates=[j for j,r in enumerate(vr) if (r['kind']=='positive')==positive]
   chosen.extend(rng.choice(candidates,min(1500,len(candidates)),replace=False))
  for j in chosen:
   r=vr[j];a=np.load(ROOT/r['feature']);end=min(len(a),max(16,round((r['end']-.775)/.08)+1));vx.append(a[end-16:end]);vy.append(r['kind']=='positive')
  vx=np.stack(vx);vy=np.array(vy,np.float32)
  checkpoint=modeldir/'checkpoint.keras';statefile=modeldir/'state.json'
  if not checkpoint.exists() and (backup/'checkpoint.keras').exists():shutil.copy2(backup/'checkpoint.keras',checkpoint);shutil.copy2(backup/'state.json',statefile)
  if checkpoint.exists():m=tf.keras.models.load_model(checkpoint);state=load(statefile)
  else:
   inp=tf.keras.Input((16,96));x=tf.keras.layers.Flatten()(inp)
   for units in (128,128):x=tf.keras.layers.Dense(units,kernel_regularizer=tf.keras.regularizers.L2(1e-5))(x);x=tf.keras.layers.LayerNormalization()(x);x=tf.keras.layers.ReLU()(x)
   out=tf.keras.layers.Dense(1,activation='sigmoid')(x);m=tf.keras.Model(inp,out,name=phrase);m.compile(optimizer=tf.keras.optimizers.Adam(1e-3),loss='binary_crossentropy');state=dict(step=0,best_loss=1e9)
  for step in range(state['step'],2000):
   rng=np.random.default_rng(SEED+step);idx=np.r_[rng.choice(pos,128),rng.choice(neg,128)];loss=float(m.train_on_batch(X[idx],y[idx]))
   if (step+1)%250==0:
    vp=m(vx,training=False);vl=float(tf.reduce_mean(tf.keras.losses.binary_crossentropy(vy[:,None],vp)));state.update(step=step+1)
    if vl<state['best_loss']:state['best_loss']=vl;m.save(modeldir/'best.keras');shutil.copy2(modeldir/'best.keras',backup/'best.keras')
    m.save(checkpoint);save(statefile,state)
    for name in ('checkpoint.keras','state.json'):shutil.copy2(modeldir/name,backup/name)
    progress('train',phrase=phrase,step=step+1,train_loss=loss,validation_loss=vl)
  save(modeldir/'complete.json',state);shutil.copy2(modeldir/'complete.json',backup/'complete.json');del m,X,vx;tf.keras.backend.clear_session();gc.collect()
 progress('train_complete')
def score(split):
 import numpy as np,gzip
 tf=tf_init();models=[tf.keras.models.load_model(ROOT/'models'/p/'best.keras',compile=False) for p in PHRASES]
 @tf.function(input_signature=[tf.TensorSpec([None,16,96],tf.float32)])
 def pred(x):return tf.concat([m(x,training=False) for m in models],axis=1)
 rows=[r for r in load(ROOT/'features.json')['rows'] if r['split']==split];results=[]
 for i,r in enumerate(rows):
  x=np.load(ROOT/r['feature']);windows=np.lib.stride_tricks.sliding_window_view(x,(16,96))[:,0];p=pred(np.ascontiguousarray(windows)).numpy()
  results.append(dict(r,probs={phrase:p[:,j].tolist() for j,phrase in enumerate(PHRASES)}))
  if i%500==0:progress('score_'+split,done=i,total=len(rows))
 path=ROOT/f'scores_{split}.json.gz'
 with gzip.open(path,'wt') as f:json.dump(results,f)
 shutil.copy2(path,BACKUP/path.name);progress('score_'+split+'_complete',cases=len(results))
def events(probs,cutoff,refractory=2.):
 out=[]
 for i,p in enumerate(probs):
  t=2.+i*.08
  if t>=3.2 and p>cutoff and (not out or t-out[-1]>=refractory):out.append(t)
 return out
def metrics(rows,phrase,cutoff):
 pos=[r for r in rows if r['kind']=='positive' and r['phrase']==phrase];ambient=[r for r in rows if r['kind']=='ambient'];hard=[r for r in rows if r['kind']=='hard'];hours=sum(r['duration'] for r in ambient)/3600
 def hit(r):return any(r['start']<=t<=r['end']+1 for t in events(r['probs'][phrase],cutoff))
 conditions={c:sum(hit(r) for r in pos if r['condition']==c)/sum(r['condition']==c for r in pos) for c in sorted({r['condition'] for r in pos})}
 return dict(cutoff=cutoff,recall=sum(map(hit,pos))/len(pos),min_condition=min(conditions.values()),recall_by_condition=conditions,faph=sum(len(events(r['probs'][phrase],cutoff)) for r in ambient)/hours,hard_fpr=sum(bool(events(r['probs'][phrase],cutoff)) for r in hard)/len(hard))
def calibrate():
 import gzip
 with gzip.open(ROOT/'scores_validation.json.gz','rt') as f:rows=json.load(f)
 result={}
 for p in PHRASES:
  grid=[metrics(rows,p,c) for c in (.05,.1,.15,.2,.25,.3,.4,.5,.6,.7,.8,.85,.9,.95,.975,.99,.995,.999)]
  good=[r for r in grid if r['recall']>=.99 and r['min_condition']>=.95]
  result[p]=dict(selected=min(good,key=lambda r:(r['faph'],r['hard_fpr'],-r['recall'])) if good else None,grid=grid)
 save(ROOT/'operating_points.json',result);save(BACKUP/'operating_points.json',result);progress('calibrate_complete',selected={p:r['selected'] for p,r in result.items()})
def export():
 import numpy as np,gzip
 tf=tf_init();ops=load(ROOT/'operating_points.json');assert all(ops[p]['selected'] for p in PHRASES),'No valid positive-recall operating point. Keep Okay Nabu installed.'
 with gzip.open(ROOT/'scores_testing.json.gz','rt') as f:rows=json.load(f)
 report={p:metrics(rows,p,ops[p]['selected']['cutoff']) for p in PHRASES}
 assert all(report[p]['recall']>=.97 and report[p]['min_condition']>=.9 for p in PHRASES),'Held-out synthetic recall gate failed; do not deploy.'
 out=ROOT/'export';out.mkdir(exist_ok=True);inp=tf.keras.Input(batch_shape=(1,16,96),dtype=tf.float32);scaled=[]
 for p in PHRASES:
  m=tf.keras.models.load_model(ROOT/'models'/p/'best.keras',compile=False);m.trainable=False
  # Each independent cutoff maps to the service's shared >0.5 threshold.
  score=tf.keras.layers.Rescaling(1/(2*ops[p]['selected']['cutoff']))(m(inp));scaled.append(score)
 combo=tf.keras.Model(inp,tf.keras.layers.Maximum()(scaled),name='nira_ehi_nira')
 combo.export(str(ROOT/'saved_model'));conv=tf.lite.TFLiteConverter.from_saved_model(str(ROOT/'saved_model'));conv.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS];data=conv.convert();path=out/'nira_ehi_nira.tflite';path.write_bytes(data)
 it=tf.lite.Interpreter(model_content=data);it.allocate_tensors();assert it.get_input_details()[0]['shape'].tolist()==[1,16,96];assert it.get_output_details()[0]['shape'].tolist()==[1,1]
 for _ in range(10):
  x=np.random.default_rng(_).normal(size=(1,16,96)).astype(np.float32);it.set_tensor(it.get_input_details()[0]['index'],x);it.invoke();assert np.allclose(it.get_tensor(it.get_output_details()[0]['index']),combo(x).numpy(),atol=1e-4)
 # Actual combined FAPH, not the sum of per-model rates.
 ambient=[r for r in rows if r['kind']=='ambient'];hours=sum(r['duration'] for r in ambient)/3600
 def combined(r):return [max(r['probs'][p][i]/(2*ops[p]['selected']['cutoff']) for p in PHRASES) for i in range(len(r['probs'][PHRASES[0]]))]
 report['combined_faph']=sum(len(events(combined(r),.5)) for r in ambient)/hours
 report.update(all_audio_synthetic=True,human_custom_word_test_performed=False,exact_pyopen_streaming_test_pending=True,batch_frontend_timing_approximation=True,threshold_selection='validation_only',model_sha256=sha(path),head_trainer='Keras adaptation of OWW DNN topology; frozen official frontend',operating_points={p:ops[p]['selected'] for p in PHRASES})
 save(out/'evaluation.json',report);save(out/'provenance.json',load(BACKUP/'source_provenance.json'));shutil.copytree(out,BACKUP/'export',dirs_exist_ok=True);zipfile=shutil.make_archive(str(ROOT/'nyra_openwakeword_v1_candidate'),'zip',out);shutil.copy2(zipfile,BACKUP/Path(zipfile).name);progress('candidate_exported_streaming_check_required',model_sha256=sha(path),metrics=report)
if __name__=='__main__':
 phase=sys.argv[1]
 with open(ROOT/'worker.lock','w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if phase=='extract':extract()
  elif phase=='features':features()
  elif phase=='train':train()
  elif phase in ('score_validation','score_testing'):score(phase.removeprefix('score_'))
  elif phase=='calibrate':calibrate()
  elif phase=='export':export()
  else:raise ValueError(phase)
