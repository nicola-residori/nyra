from fastapi import APIRouter, Request, HTTPException
from pydantic import ValidationError
from shared.protocol.observability import LogBatch, LogRecord
router=APIRouter(prefix="/v1/logs")
@router.post("/ingest")
async def ingest(request: Request):
    raw=await request.json()
    try:
        if isinstance(raw,dict) and "records" in raw: batch=LogBatch.model_validate(raw)
        else: batch=LogBatch(records=[LogRecord.model_validate(raw)])
    except ValidationError as e:
        raise HTTPException(status_code=422,detail={"accepted":0,"rejected":1,"errors":e.errors(include_url=False)})
    count=request.app.state.observability.ingest(batch.records)
    return {"accepted":count,"rejected":0}
