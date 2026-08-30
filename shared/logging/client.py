from __future__ import annotations
import json, queue, threading, time
from pathlib import Path
from typing import Any
import httpx
from shared.protocol.observability import LogRecord,LogKind,LogLevel
from router.observability.redaction import redact

class NyraLogger:
    def __init__(self, router_url:str, ct:str, context:dict[str,str], spool_path:Path=Path("data/log-spool.jsonl"), batch_size:int=20, flush_interval:float=.5, max_spool_lines:int=10000):
        self.router_url=router_url.rstrip('/'); self.ct=ct; self.context=context; self.spool_path=Path(spool_path); self.batch_size=batch_size; self.flush_interval=flush_interval; self.max_spool_lines=max_spool_lines
        self.q=queue.Queue(); self.stop_evt=threading.Event(); self.worker=threading.Thread(target=self._run,daemon=True); self.worker.start()
    def emit(self,event:str,kind:LogKind=LogKind.EVENT,level:LogLevel=LogLevel.INFO,payload:Any=None,**params):
        rec=LogRecord(ct=self.ct,event=event,kind=kind,level=level,payload=redact(payload),params=redact(params),**self.context); self.q.put_nowait(rec); return rec
    def info(self,event:str,kind:LogKind=LogKind.EVENT,**kwargs): return self.emit(event,kind,LogLevel.INFO,**kwargs)
    def close(self): self.stop_evt.set(); self.worker.join(timeout=2)
    def _send(self,records):
        with httpx.Client(timeout=2) as c: r=c.post(self.router_url+'/v1/logs/ingest',json={'records':[x.model_dump(mode='json') for x in records]}); r.raise_for_status()
    def _spool(self,records):
        self.spool_path.parent.mkdir(parents=True,exist_ok=True); lines=[]
        if self.spool_path.exists(): lines=self.spool_path.read_text().splitlines()[-self.max_spool_lines:]
        lines += [json.dumps(x.model_dump(mode='json'),ensure_ascii=False) for x in records]; lines=lines[-self.max_spool_lines:]; self.spool_path.write_text('\n'.join(lines)+'\n')
    def _run(self):
        batch=[]; last=time.monotonic()
        while not self.stop_evt.is_set() or not self.q.empty():
            try: batch.append(self.q.get(timeout=.05))
            except queue.Empty: pass
            if batch and (len(batch)>=self.batch_size or time.monotonic()-last>=self.flush_interval or self.stop_evt.is_set()):
                try:self._send(batch)
                except Exception:self._spool(batch)
                batch=[]; last=time.monotonic()
