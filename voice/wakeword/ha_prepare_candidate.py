"""Run on the home router after candidate evaluation; never prints credentials.
Creates/reuses only the buffered provider and a separate pipeline, without
selecting it on any speaker or changing the global preferred pipeline.
"""
import asyncio,json,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import websockets
PIPELINE_NAME='Nyra - Ehi Nira'
def connection():
 values={}
 for line in Path('/opt/nyra-router/.env').read_text().splitlines():
  key,sep,value=line.partition('=')
  if sep:values[key]=value.strip().strip(chr(34)).strip(chr(39))
 return values['NYRA_HOME_ASSISTANT_URL'].rstrip('/'),values['NYRA_HOME_ASSISTANT_TOKEN']
BASE,TOKEN=connection()
def api(path,data=None):
 request=Request(BASE+path,headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'},data=None if data is None else json.dumps(data).encode())
 try:
  with urlopen(request,timeout=20) as response:return json.load(response)
 except HTTPError as error:
  body=error.read().decode(errors='replace')[:500]
  raise RuntimeError(f'Home Assistant HTTP {error.code}: {body}') from None
async def main():
 flow=api('/api/config/config_entries/flow',{'handler':'nyra_wake','show_advanced_options':False})
 if flow['type']=='form':flow=api('/api/config/config_entries/flow/'+flow['flow_id'],{'host':'192.168.0.16','port':10401})
 if flow['type']=='abort':assert flow.get('reason')=='already_configured',flow
 else:assert flow['type']=='create_entry',flow
 print('PROVIDER_CONFIGURED',flow['type'],flush=True)
 entity=None
 for _ in range(20):
  found=[s['entity_id'] for s in api('/api/states') if s['entity_id'].startswith('wake_word.') and s['attributes'].get('friendly_name')=='Nyra Italian Wake']
  if len(found)==1:entity=found[0];break
  await asyncio.sleep(1)
 assert entity,'Expected one loaded Nyra Italian Wake provider'
 async with websockets.connect(BASE.replace('http://','ws://').replace('https://','wss://')+'/api/websocket') as ws:
  await ws.recv();await ws.send(json.dumps({'type':'auth','access_token':TOKEN}));assert json.loads(await ws.recv())['type']=='auth_ok'
  async def call(i,command):
   await ws.send(json.dumps(dict(id=i,**command)))
   result=json.loads(await asyncio.wait_for(ws.recv(),20));assert result.get('success'),result
   return result['result']
  info=await call(1,{'type':'wake_word/info','entity_id':entity});assert any(w['id']=='ehi_nira_it' for w in info['wake_words'])
  listed=await call(2,{'type':'assist_pipeline/pipeline/list'});matches=[p for p in listed['pipelines'] if p['name']==PIPELINE_NAME]
  assert len(matches)<=1,'Duplicate candidate pipelines require inspection'
  if matches:
   pipeline=matches[0];assert pipeline['wake_word_entity']==entity and pipeline['wake_word_id']=='ehi_nira_it'
  else:
   original=next(p for p in listed['pipelines'] if p['name']=='Nyra').copy();original.pop('id')
   original.update(name=PIPELINE_NAME,wake_word_entity=entity,wake_word_id='ehi_nira_it')
   pipeline=await call(3,dict(type='assist_pipeline/pipeline/create',**original))
  result={'pipeline_id':pipeline['id'],'pipeline_name':PIPELINE_NAME,'wake_word_entity':entity,'wake_word_id':'ehi_nira_it','speaker_selection_changed':False}
  Path('/opt/nyra-wake/ha_pipeline.json').write_text(json.dumps(result,indent=2));print('CANDIDATE_PIPELINE_READY',json.dumps(result),flush=True)
if __name__=='__main__':asyncio.run(main())
