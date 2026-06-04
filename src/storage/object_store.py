from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRef:
    best_frame_id: str | None = None
    clip_uri: str | None = None
    frame_uri: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "best_frame_id": self.best_frame_id,
            "clip_uri": self.clip_uri,
            "frame_uri": self.frame_uri,
        }
