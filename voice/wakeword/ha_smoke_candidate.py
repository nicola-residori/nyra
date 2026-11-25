"""Silent synthetic wake+STT integration test. Never runs intents or TTS."""
import asyncio,json,subprocess,time
from pathlib import Path
import websockets
values={}
for line in Path('/opt/nyra-router/.env').read_text().splitlines():
 key,sep,value=line.partition('=')
 if sep:values[key]=value.strip().strip(chr(34)).strip(chr(39))
BASE=values['NYRA_HOME_ASSISTANT_URL'].rstrip('/');TOKEN=values['NYRA_HOME_ASSISTANT_TOKEN']
async def main():
 pipeline=json.loads(Path('/opt/nyra-wake/ha_pipeline.json').read_text());root=Path('/tmp/nyra-italian-benchmark')
 pcm=subprocess.check_output([str(root/'env/bin/python'),str(root/'render_ha_smoke.py')],cwd=root);assert len(pcm)==320000
 async with websockets.connect(BASE.replace('http://','ws://').replace('https://','wss://')+'/api/websocket') as ws:
  await ws.recv();await ws.send(json.dumps({'type':'auth','access_token':TOKEN}));assert json.loads(await ws.recv())['type']=='auth_ok'
  await ws.send(json.dumps({'id':1,'type':'assist_pipeline/run','pipeline':pipeline['pipeline_id'],'start_stage':'wake_word','end_stage':'stt','input':{'sample_rate':16000,'timeout':15,'no_vad':True}}))
  async def send_audio(handler):
   began=time.monotonic()
   for offset in range(0,len(pcm),3200):
    await ws.send(bytes([handler])+pcm[offset:offset+3200]);await asyncio.sleep(max(0,(offset+3200)/32000-(time.monotonic()-began)))
   await ws.send(bytes([handler]))
  sender=None;events=[];text='';wake=None
  try:
   async with asyncio.timeout(90):
    while True:
     message=json.loads(await asyncio.wait_for(ws.recv(),45))
     if message.get('success') is False:raise RuntimeError(message.get('error'))
     event=message.get('event',{});kind=event.get('type');data=event.get('data',{})
     if not kind:continue
     events.append(kind);print('HA_SMOKE_EVENT',kind,flush=True)
     if kind=='run-start':sender=asyncio.create_task(send_audio(data['runner_data']['stt_binary_handler_id']))
     if kind=='wake_word-end':wake=data.get('wake_word_output')
     if kind=='stt-end':text=data.get('stt_output',{}).get('text','')
     if kind=='error':raise RuntimeError(data)
     if kind=='run-end':break
  finally:
   if sender:
    sender.cancel();await asyncio.gather(sender,return_exceptions=True)
  assert wake and wake.get('wake_word_id')=='ehi_nira_it',wake
  assert 'apri' in text.lower() and 'finestr' in text.lower(),repr(text)
  result=dict(pipeline=pipeline['pipeline_id'],wake_word=wake,synthetic_transcript=text,events=events,intents_executed=False,tts_played=False,human_test=False)
  Path('/opt/nyra-wake/ha_smoke_result.json').write_text(json.dumps(result,indent=2));print('SILENT_WAKE_AND_JOINED_COMMAND_VERIFIED',json.dumps(result),flush=True)
if __name__=='__main__':asyncio.run(main())
