from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable

from shared.protocol.ids import new_request_id, new_session_id


@dataclass
class _Session:
    session_id: str
    active_request_id: str | None
    last_activity: float


class SessionManager:
    def __init__(self, ttl_seconds: float = 300.0, clock: Callable[[], float] | None = None):
        self._ttl_seconds = ttl_seconds
        self._clock = clock or monotonic
        self._sessions: dict[str, _Session] = {}

    def _get_live(self, conversation_key: str) -> _Session | None:
        self.expire()
        session = self._sessions.get(conversation_key)
        if session is not None:
            session.last_activity = self._clock()
        return session

    def get_or_create_session(self, conversation_key: str) -> str:
        session = self._get_live(conversation_key)
        if session is None:
            session = _Session(new_session_id(), None, self._clock())
            self._sessions[conversation_key] = session
        return session.session_id

    def get_request_id(self, conversation_key: str) -> str:
        session = self._get_live(conversation_key)
        if session is None:
            self.get_or_create_session(conversation_key)
            session = self._sessions[conversation_key]
        if session.active_request_id is None:
            session.active_request_id = new_request_id()
        return session.active_request_id

    def preserve_request(self, conversation_key: str) -> None:
        session = self._get_live(conversation_key)
        if session is not None:
            session.last_activity = self._clock()

    def complete_request(self, conversation_key: str) -> None:
        session = self._get_live(conversation_key)
        if session is not None:
            session.active_request_id = None

    def close_session(self, conversation_key: str) -> None:
        self._sessions.pop(conversation_key, None)

    def expire(self) -> None:
        now = self._clock()
        expired = [
            key for key, value in self._sessions.items()
            if now - value.last_activity > self._ttl_seconds
        ]
        for key in expired:
            self._sessions.pop(key, None)
