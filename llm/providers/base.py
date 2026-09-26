from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class ProviderErrorKind(str, Enum):
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    CONNECTION = "CONNECTION"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_STRUCTURED_OUTPUT = "INVALID_STRUCTURED_OUTPUT"
    OTHER = "OTHER"


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ProviderRequest:
    purpose: str
    model: str
    messages: Sequence[Mapping[str, Any]]
    response_schema: Mapping[str, Any]


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    provider: str
    model: str
    usage: ProviderUsage = ProviderUsage()


@dataclass(frozen=True)
class ProviderError(Exception):
    kind: ProviderErrorKind
    provider: str
    model: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class ProviderAdapter(ABC):
    @abstractmethod
    async def infer(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError
