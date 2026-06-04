from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedROI:
    x: float
    y: float
    width: float
    height: float

    def to_pixels(self, image_width: int, image_height: int) -> tuple[int, int, int, int]:
        left = round(self.x * image_width)
        top = round(self.y * image_height)
        right = round((self.x + self.width) * image_width)
        bottom = round((self.y + self.height) * image_height)
        return left, top, right, bottom

    @classmethod
    def from_xywh(cls, values: list[float] | tuple[float, float, float, float]) -> "NormalizedROI":
        if len(values) != 4:
            raise ValueError("ROI requires [x, y, width, height].")
        return cls(float(values[0]), float(values[1]), float(values[2]), float(values[3]))
