from __future__ import annotations

from src.api.schemas import FrameQuality


def classify_frame_quality(
    blur_score: float | None = None,
    is_frozen: bool = False,
    is_black_frame: bool = False,
    min_blur_score: float | None = None,
) -> FrameQuality:
    status = "good"
    if is_black_frame:
        status = "black"
    elif is_frozen:
        status = "frozen"
    elif min_blur_score is not None and blur_score is not None and blur_score < min_blur_score:
        status = "blurred"
    return FrameQuality(
        blur_score=blur_score,
        is_frozen=is_frozen,
        is_black_frame=is_black_frame,
        quality_status=status,
    )
