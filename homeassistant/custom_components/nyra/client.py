from __future__ import annotations

import httpx

from shared.protocol.requests import NyraRequest, NyraRequestResponse
from shared.protocol.service import ServiceState, ServiceStatusResponse

from .const import (
    DEFAULT_TIMEOUT_SECONDS, ENROLLMENT_PATH, READY_PATH, REQUEST_PATH,
    WAKE_WORD_CAPTURE_PATH,
)


class NyraRouterError(RuntimeError):
    pass


class NyraRouterUnavailable(NyraRouterError):
    pass


class NyraRouterRejected(NyraRouterError):
    pass


class NyraRouterInvalidResponse(NyraRouterError):
    pass


class NyraRouterClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token or None
        self.timeout = timeout
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def async_ready(self) -> bool:
        try:
            response = await self._client.get(
                f"{self.base_url}{READY_PATH}", headers=self.headers, timeout=self.timeout
            )
            response.raise_for_status()
            status = ServiceStatusResponse.model_validate(response.json())
            return status.status is ServiceState.READY
        except (httpx.HTTPError, ValueError):
            return False

    async def async_execute(self, request: NyraRequest) -> NyraRequestResponse:
        try:
            response = await self._client.post(
                f"{self.base_url}{REQUEST_PATH}",
                headers=self.headers,
                json=request.model_dump(mode="json"),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise NyraRouterUnavailable("Nyra Router is unavailable") from exc

        if 400 <= response.status_code < 500:
            raise NyraRouterRejected(f"Router rejected request with HTTP {response.status_code}")
        if response.status_code >= 500:
            raise NyraRouterUnavailable(f"Router failed with HTTP {response.status_code}")
        try:
            response.raise_for_status()
            return NyraRequestResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise NyraRouterInvalidResponse("Router returned an invalid response") from exc

    async def _async_enrollment_request(self, method: str, path: str, payload=None) -> dict:
        try:
            response = await self._client.request(
                method, f"{self.base_url}{path}", headers=self.headers,
                json=payload, timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise NyraRouterUnavailable("Nyra Router is unavailable") from exc
        if 400 <= response.status_code < 500:
            raise NyraRouterRejected(f"Router rejected enrollment with HTTP {response.status_code}")
        if response.status_code >= 500:
            raise NyraRouterUnavailable(f"Router failed enrollment with HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise NyraRouterInvalidResponse("Router returned invalid enrollment JSON") from exc
        required = {"session_id", "profile_user_id", "source_id", "language", "target_count",
                    "accepted_count", "accepted_sample_ids", "status", "current_phrase"}
        if not isinstance(data, dict) or not required.issubset(data) or data["status"] not in {
            "ACTIVE", "COMPLETED", "TERMINATED"
        }:
            raise NyraRouterInvalidResponse("Router returned an invalid enrollment response")
        return data

    async def async_start_enrollment(self, *, profile_user_id: str, source_id: str,
                                     language: str, target_count: int = 6) -> dict:
        return await self._async_enrollment_request("POST", ENROLLMENT_PATH, {
            "profile_user_id": profile_user_id, "source_id": source_id,
            "language": language, "target_count": target_count,
        })

    async def async_record_enrollment_attempt(self, session_id: str, result: dict) -> dict:
        return await self._async_enrollment_request(
            "POST", f"{ENROLLMENT_PATH}/{session_id}/attempts", result
        )

    async def async_get_active_enrollment(self, source_id: str) -> dict | None:
        try:
            return await self._async_enrollment_request(
                "GET", f"{ENROLLMENT_PATH}/active/{source_id}"
            )
        except NyraRouterRejected as exc:
            if "HTTP 404" in str(exc):
                return None
            raise

    async def async_terminate_enrollment(self, session_id: str, reason: str) -> dict:
        return await self._async_enrollment_request(
            "POST", f"{ENROLLMENT_PATH}/{session_id}/terminate", {"reason": reason}
        )

    async def _async_wake_word_request(self, method: str, path: str, payload=None) -> dict:
        try:
            response = await self._client.request(
                method, f"{self.base_url}{path}", headers=self.headers,
                json=payload, timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise NyraRouterUnavailable("Nyra Router is unavailable") from exc
        if 400 <= response.status_code < 500:
            raise NyraRouterRejected(
                f"Router rejected wake-word capture with HTTP {response.status_code}"
            )
        if response.status_code >= 500:
            raise NyraRouterUnavailable(
                f"Router failed wake-word capture with HTTP {response.status_code}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise NyraRouterInvalidResponse("Router returned invalid wake-word JSON") from exc
        required = {"session_id", "user_id", "source_id", "language", "wake_word_text",
                    "status", "sample_id", "reason_code"}
        if not isinstance(data, dict) or not required.issubset(data) or data["status"] not in {
            "ACTIVE", "ACCEPTED", "REJECTED", "FAILED"
        }:
            raise NyraRouterInvalidResponse("Router returned an invalid wake-word response")
        return data

    async def async_start_wake_word_capture(self, *, user_id: str, source_id: str,
                                            language: str, wake_word_text: str) -> dict:
        return await self._async_wake_word_request("POST", WAKE_WORD_CAPTURE_PATH, {
            "user_id": user_id, "source_id": source_id, "language": language,
            "wake_word_text": wake_word_text,
        })

    async def async_get_active_wake_word_capture(self, source_id: str) -> dict | None:
        try:
            return await self._async_wake_word_request(
                "GET", f"{WAKE_WORD_CAPTURE_PATH}/active/{source_id}"
            )
        except NyraRouterRejected as exc:
            if "HTTP 404" in str(exc):
                return None
            raise

    async def async_complete_wake_word_capture(self, session_id: str, result: dict) -> dict:
        return await self._async_wake_word_request(
            "POST", f"{WAKE_WORD_CAPTURE_PATH}/{session_id}/result", result
        )

    async def async_wake_word_sample_count(self, wake_word_text: str) -> int:
        try:
            response = await self._client.get(
                f"{self.base_url}{WAKE_WORD_CAPTURE_PATH}/sample-count",
                headers=self.headers, params={"wake_word_text": wake_word_text},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NyraRouterUnavailable("Wake-word dataset count is unavailable") from exc
        count = data.get("sample_count") if isinstance(data, dict) else None
        if type(count) is not int or count < 0:
            raise NyraRouterInvalidResponse("Router returned an invalid sample count")
        return count

    async def async_close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
