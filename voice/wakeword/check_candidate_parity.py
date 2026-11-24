from pathlib import Path
import json,gzip,importlib.util,hashlib
import numpy as np
from evaluate_candidate import render
from cached_frontend import CachedStreamFront
from pyopen_wakeword import OpenWakeWord
root=Path('testdata');spec=importlib.util.spec_from_file_location('old',root/'original_worker.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
plan=json.loads((root/'plan.json').read_text());lookup={(x['row']['id'],x['condition']):x for x in plan if x['split']=='validation'}
with gzip.open(root/'validation_scores.json.gz','rt') as f:rows=json.load(f)
chosen=[rows[0],next(r for r in rows if r['kind']=='hard'),next(r for r in rows if r['kind']=='ambient')]
front=CachedStreamFront();head=OpenWakeWord.from_model(Path('primary_ehi_nira.tflite'))
for r in chosen:
 pcm=render(lookup[(r['id'],r['condition'])],root,old);front.reset();head.reset();probs=[];times=[]
 for off in range(0,len(pcm),1280):
  chunk=pcm[off:off+1280]
  if len(chunk)<1280:chunk=np.pad(chunk,(0,1280-len(chunk)))
  for emb in front.process_streaming(chunk.tobytes()):
   for p in head.process_streaming(emb):probs.append(p);times.append(min((off+1280)/16000,len(pcm)/16000))
 expected=r['probs']['ehi_nira_it'];assert len(probs)==len(expected),(len(probs),len(expected));error=float(np.max(np.abs(np.array(probs)-expected)));assert error<1e-4,error
 assert np.allclose(times,r['times'],atol=5e-6)
 print('PRIMARY_PARITY_PASSED',r['id'],r['condition'],len(probs),error,flush=True)
for name,sha in json.loads(Path('manifest.json').read_text()).items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha
print('ALL_MANIFEST_HASHES_PASSED',flush=True)
