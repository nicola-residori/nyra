"""Read-only semantic/check/resolve probe. Never calls an execution endpoint.
Run from a Nyra source checkout/environment on the trusted home network.
"""
import json
import uuid
from urllib.request import Request, urlopen
from shared.protocol.semantic import SemanticResult
from router.semantic_skill_bridge import SemanticSkillBridge

def call(host,path,data=None):
    req=Request('http://'+host+':8090'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urlopen(req,timeout=50) as response:return json.load(response)

def main():
    for host in ['192.168.0.16','192.168.0.15','192.168.0.11']:
        print('READY',host,call(host,'/ready').get('status'),flush=True)
    c={'request_id':'req_'+str(uuid.uuid4()),'trace_id':'trc_'+str(uuid.uuid4())}
    cases=[('esegui lo script della buonanotte','script.buonanotte',False),('attiva la buonanotte','script.buonanotte',False),('pulisci zona giorno','script.pulizia_zona_giorno_standard',False),('aspira zona giorno','script.pulizia_zona_giorno_aspirazione',False),('pulisci profondamente zona giorno','script.pulizia_zona_giorno_profonda',False),('puoi passare solo l aspirapolvere in cucina?','script.pulizia_cucina_aspirazione',True),('pulisci zona giorno a fondo','script.pulizia_zona_giorno_profonda',True)]
    records=[]
    for phrase,expected,use_llm in cases:
        payload={'correlation':c,'text':phrase,'language':'it','context':{'area':'Soggiorno'}}
        if use_llm:
            initial=call('192.168.0.15','/v1/skills/check',payload)
            assert initial['outcome']=='MISS',(phrase,initial)
            sem=call('192.168.0.11','/v1/llm/semantic',{'purpose':'SEMANTIC','context':{'language':'it','current_user_input':phrase,'operational':{'mode':'skill_routing'},'area':'Soggiorno'}})
            accepted=SemanticSkillBridge().accept(SemanticResult.model_validate(sem),text=phrase)
            assert accepted is not None,sem
            payload['semantic']=accepted.model_dump(mode='json')
        checked=call('192.168.0.15','/v1/skills/check',payload)
        assert checked['outcome']=='HANDLED',checked
        m=checked['match']['metadata']
        resolved=call('192.168.0.16','/v1/capabilities/home-assistant/resolve',{'correlation':c,'reference':{'reference':m['reference'],'resource_type':m['resource_type'],'cardinality':'ONE'},'trusted_context':{'area':'Soggiorno'}})
        ids=[x['resource']['resource_id'] for x in resolved['candidates']]
        assert ids==[expected],(phrase,ids)
        records.append({'phrase':phrase,'resolved':ids,'live_llm':use_llm})
        print('CHECK_RESOLVE_PASS',phrase,ids,'LLM',use_llm,flush=True)
    from pathlib import Path
    Path('/tmp/nyra-command-live-check.json').write_text(json.dumps({'household_actions_executed':False,'checks':records},indent=2))
if __name__=='__main__':main()
