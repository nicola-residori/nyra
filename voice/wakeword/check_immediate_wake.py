"""Synthetic cold-stream starts, including speech in the very first sample."""
from pathlib import Path
import json,importlib.util
import numpy as np
from candidate_engine import CandidateEngine
from evaluate_candidate import render
root=Path('testdata');spec=importlib.util.spec_from_file_location('original',root/'original_worker.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
plan=json.loads((root/'plan.json').read_text());item=next(x for x in plan if x['split']=='validation' and x['row']['phrase']=='ehi_nira_it' and x['condition']=='clean__floor-60');wave=render(item,root,old);engine=CandidateEngine('.',history_limit=64);results=[]
for lead in [0,.08,.2,.5,1.]:
 pcm=wave[round((4-lead)*16000):];engine.reset()
 for off in range(0,len(pcm),1280):
  chunk=pcm[off:off+1280]
  if len(chunk)<1280:chunk=np.pad(chunk,(0,1280-len(chunk)))
  engine.feed(chunk.tobytes())
 good=[e for e in engine.detections if lead<=e['t']<=lead+item['row']['duration']+1]
 result=dict(lead_seconds=lead,detected=bool(good),candidates=engine.candidates,detections=engine.detections);results.append(result);print('IMMEDIATE_WAKE',lead,bool(good),[(e['candidate_t'],e['probability']) for e in engine.candidates],flush=True)
Path('immediate_wake_result.json').write_text(json.dumps(results,indent=2));assert all(r['detected'] for r in results),results
