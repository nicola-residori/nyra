from __future__ import annotations
import httpx
from shared.protocol.llm import LlmRequest, ReasoningResult

class LlmUnavailable(RuntimeError):
    pass

class LlmClient:
    def __init__(self, base_url:str, timeout:float=8.0, client=None):
        self.base_url=base_url.rstrip("/")
        self.timeout=float(timeout)
        self.client=client

    async def diagnostics(self) -> dict:
        own=self.client is None
        client=self.client or httpx.AsyncClient(timeout=self.timeout)
        try:
            response=await client.get(f"{self.base_url}/v1/llm/diagnostics")
            response.raise_for_status()
            payload=response.json()
            if not isinstance(payload,dict) or not isinstance(payload.get("items"),list): raise ValueError("invalid LLM diagnostics response")
            return payload
        except (httpx.TimeoutException,httpx.TransportError,httpx.HTTPStatusError,ValueError) as exc:
            raise LlmUnavailable("LLM diagnostics unavailable") from exc
        finally:
            if own: await client.aclose()

    async def reason(self, request:LlmRequest)->ReasoningResult:
        own=self.client is None
        client=self.client or httpx.AsyncClient(timeout=self.timeout)
        try:
            response=await client.post(f"{self.base_url}/v1/llm/reason",json=request.model_dump(mode="json"))
            response.raise_for_status()
            return ReasoningResult.model_validate(response.json())
        except (httpx.TimeoutException,httpx.TransportError,httpx.HTTPStatusError,ValueError) as exc:
            raise LlmUnavailable("LLM service unavailable") from exc
        finally:
            if own: await client.aclose()
