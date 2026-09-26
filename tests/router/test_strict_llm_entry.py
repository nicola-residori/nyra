import pytest
from router.lifecycle.service import LifecycleDecision,SkillMatch
from shared.protocol.skills import SkillOutcome
from shared.protocol.requests import RequestStatus
from tests.router.test_request_lifecycle import service,request,SkillPort,LlmPort

@pytest.mark.asyncio
async def test_only_check_miss_enters_llm(tmp_path):
    llm=LlmPort()
    skill=SkillPort(match=False)
    skill.check=lambda *args,**kwargs: _check(SkillMatch(matched=False,outcome=SkillOutcome.FAILED,error_code="NO"))
    svc,_,_=service(tmp_path,skill_port=skill,llm_port=llm)
    result=await svc.execute(request(kind="ha_assist"))
    assert result.status is RequestStatus.FAILED and llm.calls==0

async def _check(value): return value

@pytest.mark.asyncio
async def test_execute_llm_fallback_flag_does_not_enter_llm(tmp_path):
    llm=LlmPort(); skill=SkillPort(match=True,decision=LifecycleDecision(status=RequestStatus.FAILED,llm_fallback=True))
    svc,_,_=service(tmp_path,skill_port=skill,llm_port=llm)
    result=await svc.execute(request(kind="ha_assist"))
    assert result.status is RequestStatus.FAILED and llm.calls==0
