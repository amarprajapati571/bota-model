from __future__ import annotations

from dataclasses import dataclass

from src.layout.roi import NormalizedROI


@dataclass(frozen=True)
class LayoutConfig:
    table_id: str
    camera_id: str
    rois: dict[str, NormalizedROI]
    expected_resolution: tuple[int, int] | None = None
    config_id: str = "manual-layout"

    def roi_pixels(self, name: str, image_width: int, image_height: int) -> tuple[int, int, int, int]:
        if name not in self.rois:
            raise KeyError(f"Unknown ROI: {name}")
        return self.rois[name].to_pixels(image_width, image_height)
