"""Platform-neutral musical intent; entity IDs, service names and URIs are never input."""

from .capabilities import CapabilityCorrelation
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MusicCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "PLAY",
        "PAUSE",
        "RESUME",
        "STOP",
        "NEXT",
        "PREVIOUS",
        "VOLUME_UP",
        "VOLUME_DOWN",
        "VOLUME",
        "TRANSFER",
        "GROUP",
    ]
    query: str | None = Field(default=None, min_length=1, max_length=300)
    media_type: Literal["artist", "album", "track", "playlist", "radio"] | None = None
    areas: list[str] = Field(default_factory=list, max_length=8)
    volume: int | None = Field(default=None, ge=0, le=100, strict=True)

    @model_validator(mode="after")
    def valid_operation(self):
        if self.action == "PLAY":
            if not self.query or not self.query.strip() or "://" in self.query:
                raise ValueError("PLAY requires a catalog query")
        elif self.query is not None or self.media_type is not None:
            raise ValueError("catalog fields are only valid for PLAY")
        if (self.action == "VOLUME") != (self.volume is not None):
            raise ValueError("volume is required only for VOLUME")
        if self.action in ("TRANSFER", "GROUP") and not self.areas:
            raise ValueError("destination required")
        if any(
            not a.strip() or len(a) > 80 or "://" in a or a.startswith("media_player.")
            for a in self.areas
        ):
            raise ValueError("area names required")
        return self


class MusicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    language: str = Field(default="it", max_length=30)
    correlation: CapabilityCorrelation
    command: MusicCommand | None = None
    selection: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.command is None) == (self.selection is None):
            raise ValueError("one command or selection required")
        return self
