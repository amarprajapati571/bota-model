from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True)
class RawFrame:
    frame_id: str
    payload: object
    server_ts_utc: object
    stream_pts_ms: int | None = None


class StreamReader(Protocol):
    def frames(self) -> Iterable[RawFrame]:
        """Yield decoded frames from an authorized stream."""


class IterableStreamReader:
    def __init__(self, frames: Iterable[RawFrame]) -> None:
        self._frames = frames

    def frames(self) -> Iterable[RawFrame]:
        yield from self._frames
