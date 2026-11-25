"""Verify complete frozen evaluation and archive its facts, without deploying."""
from pathlib import Path
import json,hashlib,collections,math,shutil,time
import numpy as np
from evaluate_candidate import report
ROOT=Path('/tmp/nyra-italian-benchmark');OUT=Path('/opt/nyra-wake/recovery')
def verify_identity(result,item):
 row=item['row']
 expected=dict(split=item['split'],condition=item['condition'],id=row['id'],kind=row['kind'],phrase=row['phrase'],variant=row.get('variant','negative'),voice=row.get('family','unknown').split('-')[0])
 for name,value in expected.items():assert result[name]==value,(result.get('key'),name,result[name],value)
 assert math.isfinite(result['duration']) and math.isclose(result['duration'],5+row['duration'],rel_tol=0,abs_tol=1/16000),(result.get('key'),'duration')
def main():
 plan=json.loads((ROOT/'testdata/plan.json').read_text());raw=(ROOT/'evaluation/results.jsonl').read_bytes();raw=raw[:raw.rfind(b'\n')+1];rows=[json.loads(x) for x in raw.splitlines()]
 if len(rows)<len(plan):
  print(json.dumps(dict(ready=False,completed=len(rows),expected=len(plan))));return
 expected={hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest():x for x in plan};assert len(expected)==len(plan)==len(rows)==6680
 assert len({r['key'] for r in rows})==len(rows) and {r['key'] for r in rows}==set(expected)
 manifest=json.loads((ROOT/'manifest.json').read_text())
 for name,sha in manifest.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,name
 config=json.loads((ROOT/'config.json').read_text());configsha=hashlib.sha256((ROOT/'config.json').read_bytes()).hexdigest()
 assert all(r['config_sha256']==configsha for r in rows)
 expected_counts=collections.Counter((x['split'],x['row']['kind'],x['row']['phrase']) for x in plan);actual_counts=collections.Counter((x['split'],x['kind'],x['phrase']) for x in rows);assert actual_counts==expected_counts
 latency=[]
 for r in rows:
  item=expected[r['key']];verify_identity(r,item);end=4+item['row']['duration']
  for e in r['candidates']:
   p=e.get('probability');assert p is None or math.isfinite(p) and 0<=p<=1
  if r['kind']=='positive' and r['phrase']=='ehi_nira_it':
   good=[e for e in r['detections'] if 4<=e['t']<=end+1];assert bool(good)==r['hit']
   if r['split']=='testing' and good:latency.append(good[0]['t']-end)
 metrics=report(rows)
 for split,m in metrics.items():
  m['minimum_condition_recall']=min(a/b for a,b in m['by_condition'].values())
  m['minimum_variant_recall']=min(a/b for a,b in m['by_variant'].values())
  m['minimum_voice_recall']=min(a/b for a,b in m['by_voice'].values())
 strict=metrics['validation']['recall']>=.99 and metrics['validation']['faph']<=2 and metrics['validation']['minimum_condition_recall']>=.9 and metrics['validation']['minimum_variant_recall']>=.95 and metrics['validation']['minimum_voice_recall']>=.95 and metrics['validation']['preword']==0 and metrics['validation']['hard_hits']/metrics['validation']['hard_total']<=.05
 result=dict(completed_cases=len(rows),expected_cases=len(plan),metrics=metrics,config_sha256=configsha,model_manifest=manifest,results_sha256=hashlib.sha256(raw).hexdigest(),source_plan_sha256=hashlib.sha256((ROOT/'testdata/plan.json').read_bytes()).hexdigest(),updated=time.time(),original_strict_validation_target_passed=bool(strict),all_audio_synthetic=True,human_room_test_performed=False,test_voice_identities_overlap_training=True,audio_clock_detection_delay_testing_seconds=dict(p50=float(np.percentile(latency,50)),p90=float(np.percentile(latency,90)),note='Input-audio timestamps only; excludes verifier compute, transport and concurrent-client queue time.'),deployment_authorized_by_report=False,limits=['Synthetic validation and testing do not establish human-speaker or room reliability.','False activations/hour measured on synthetic stress streams, not real TV or room recordings.','This report does not change the frozen thresholds or approve a production deployment.'])
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'results.partial').write_bytes(raw);(OUT/'results.partial').replace(OUT/'results.jsonl');(OUT/'final_report.json').write_text(json.dumps(result,indent=2));shutil.copy2(ROOT/'testdata/plan.json',OUT/'plan.json');shutil.copy2(ROOT/'manifest.json',OUT/'model_manifest.json')
 compact={s:{k:v for k,v in m.items() if not k.startswith('by_')} for s,m in metrics.items()};print(json.dumps(dict(ready=True,completed=len(rows),metrics=compact,strict_validation_target_passed=bool(strict)),indent=2))
if __name__=='__main__':main()
