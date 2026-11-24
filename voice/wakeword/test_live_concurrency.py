"""Two synthetic clients, actual N100 engine, real-time streaming; no live audio."""
import asyncio,json,time,importlib.util,sys,argparse
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'homeassistant/custom_components'))
from nyra_wake.stream import detect_stream
from evaluate_candidate import render
from scipy.io.wavfile import read
async def main():
 args=argparse.ArgumentParser();args.add_argument("--max-latency",type=float,default=3.5);args=args.parse_args()
 root=Path('testdata');spec=importlib.util.spec_from_file_location('original',root/'original_worker.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 plan=json.loads((root/'plan.json').read_text());item=next(x for x in plan if x['split']=='validation' and x['row']['phrase']=='ehi_nira_it' and x['condition']=='clean__floor-60');pcm=render(item,root,old)
 hard=next(x for x in plan if x['row']['kind']=='hard' and x['row']['text']=='Apri la finestra');sr,command=read(root/hard['row']['path']);assert sr==16000
 end=round((4+item['row']['duration'])*16000);start=end+1280;data=np.zeros(16000*10,dtype='<i2');data[:len(pcm)]=pcm;data[start:start+len(command)]=command;blob=data.tobytes()
 async def client(index):
  consumed=0;began=time.monotonic()
  async def audio():
   nonlocal consumed
   for off in range(0,len(blob),640):
    await asyncio.sleep(max(0,(off/32000+.02)-(time.monotonic()-began)));consumed=off+640;yield blob[off:off+640],off/32
  d,q=await asyncio.wait_for(detect_stream(audio(),'127.0.0.1',10401,'ehi_nira_it'),18)
  assert d is not None and q
  cut=round(max(0,d.timestamp-1000)*32);queued=b''.join(x[0] for x in q)
  retained=queued==blob[cut:consumed]
  assert cut<=start*2,'Beginning of the command was trimmed'
  latency=time.monotonic()-began-d.timestamp/1000
  return dict(client=index,candidate_timestamp_ms=d.timestamp,latency_after_candidate_seconds=latency,buffered_command_bytes=len(queued),upstream_received_ms=consumed/32,first_buffered_timestamp=q[0][1],full_command_retained=retained)
 results=await asyncio.gather(client(1),client(2));Path('concurrency_result.json').write_text(json.dumps(results,indent=2));print('TWO_CLIENT_REAL_ENGINE_RESULTS',json.dumps(results),flush=True)
 assert all(r['full_command_retained'] for r in results),results
 assert max(r['latency_after_candidate_seconds'] for r in results)<args.max_latency,results
if __name__=='__main__':asyncio.run(main())
