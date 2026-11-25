from pathlib import Path
import json,importlib.util
import numpy as np
from candidate_engine import CandidateEngine
from evaluate_candidate import render
root=Path('testdata')
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
old=load('approved_renderer',root/'original_worker.py');frozen=load('evaluated_engine',Path('candidate_engine_evaluation_frozen.py'))
new=CandidateEngine('.',history_limit=64);previous=frozen.CandidateEngine('.',skip_verifier=True);previous.session=new.session
plan=json.loads((root/'plan.json').read_text());chosen=[next(x for x in plan if x['split']=='validation' and x['row']['phrase']=='ehi_nira_it' and x['condition']==c) for c in ['clean__floor-60','off_axis_strong__floor-45']];chosen.append(next(x for x in plan if x['split']=='validation' and x['row']['kind']=='hard'))
def clean(rows):return [{k:v for k,v in r.items() if k!='verifier_wall_seconds'} for r in rows]
for item in chosen:
 pcm=render(item,root,old)
 for engine in (previous,new):
  engine.reset()
  for offset in range(0,len(pcm),1280):
   a=pcm[offset:offset+1280]
   if len(a)<1280:a=np.pad(a,(0,1280-len(a)))
   engine.feed(a.tobytes())
 assert clean(previous.candidates)==clean(new.candidates)
 assert clean(previous.detections)==clean(new.detections)
 print('ENGINE_HISTORY_REFACTOR_PARITY',item['row']['id'],item['condition'],len(new.candidates),len(new.detections),flush=True)
