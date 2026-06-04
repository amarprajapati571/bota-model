from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import re

from src.api.schemas import ClockObservation, ClockStatus


TIME_RE = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*$")
DIGITS_RE = re.compile(r"\D+")


def parse_clock_text(text: str | None, confidence: float = 1.0) -> ClockObservation:
    if not text:
        return ClockObservation(text, None, None, confidence, ClockStatus.MISSING)

    match = TIME_RE.match(text)
    if match:
        maybe_hour, minute, second = match.groups()
        hour = int(maybe_hour or 0)
        minute_i = int(minute)
        second_i = int(second)
        return _build_observation(text, hour, minute_i, second_i, confidence)

    digits = DIGITS_RE.sub("", text)
    if len(digits) == 6:
        hour, minute, second = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
        return _build_observation(text, hour, minute, second, confidence)
    if len(digits) == 4:
        minute, second = int(digits[:2]), int(digits[2:4])
        return _build_observation(text, 0, minute, second, confidence)

    return ClockObservation(text, None, None, confidence, ClockStatus.INVALID)


def _build_observation(
    text: str, hour: int, minute: int, second: int, confidence: float
) -> ClockObservation:
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return ClockObservation(text, None, None, confidence, ClockStatus.INVALID)
    parsed = f"{hour:02d}:{minute:02d}:{second:02d}"
    return ClockObservation(text, parsed, hour * 3600 + minute * 60 + second, confidence)


@dataclass
class ClockSmoother:
    min_confidence: float = 0.85
    max_history: int = 8
    max_clock_gap_seconds: float = 2.0
    _history: deque[tuple[datetime, ClockObservation]] = field(default_factory=deque)

    def update(self, observed: ClockObservation, timestamp: datetime) -> ClockObservation:
        if observed.status != ClockStatus.VALID or observed.confidence < self.min_confidence:
            return observed

        if self._history and observed.seconds_of_day is not None:
            _, previous = self._history[-1]
            if previous.seconds_of_day is not None and not self._is_plausible(previous, observed):
                return ClockObservation(
                    observed.text_raw,
                    observed.parsed_time,
                    observed.seconds_of_day,
                    observed.confidence,
                    ClockStatus.INVALID,
                )

        self._history.append((timestamp, observed))
        while len(self._history) > self.max_history:
            self._history.popleft()
        return observed

    def confirmed_start_boundary(self, start_window: tuple[int, int], min_frames: int) -> bool:
        valid_seconds = [
            obs.seconds_of_day % 60
            for _, obs in self._history
            if obs.status == ClockStatus.VALID and obs.seconds_of_day is not None
        ]
        if len(valid_seconds) < min_frames:
            return False
        lower, upper = start_window
        recent = valid_seconds[-min_frames:]
        return all(lower <= second <= upper for second in recent)

    @staticmethod
    def is_minute_rollover(previous: ClockObservation, current: ClockObservation) -> bool:
        if previous.seconds_of_day is None or current.seconds_of_day is None:
            return False
        previous_second = previous.seconds_of_day % 60
        current_second = current.seconds_of_day % 60
        return previous_second in (58, 59) and current_second in (0, 1, 2)

    @staticmethod
    def _is_plausible(previous: ClockObservation, current: ClockObservation) -> bool:
        if previous.seconds_of_day is None or current.seconds_of_day is None:
            return False
        delta = current.seconds_of_day - previous.seconds_of_day
        if delta < 0:
            delta += 24 * 60 * 60
        return 0 <= delta <= 2
