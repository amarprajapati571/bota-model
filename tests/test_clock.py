from __future__ import annotations

from datetime import datetime, timezone
import unittest

from src.api.schemas import ClockStatus
from src.engine.clock import ClockSmoother, parse_clock_text


class ClockTests(unittest.TestCase):
    def test_parse_common_clock_formats(self) -> None:
        self.assertEqual(parse_clock_text("184357").parsed_time, "18:43:57")
        self.assertEqual(parse_clock_text("18:43:57").seconds_of_day, 67437)
        self.assertEqual(parse_clock_text("43:57").parsed_time, "00:43:57")

    def test_invalid_clock(self) -> None:
        observed = parse_clock_text("99:99:99")
        self.assertEqual(observed.status, ClockStatus.INVALID)

    def test_confirmed_boundary_requires_multiple_frames(self) -> None:
        smoother = ClockSmoother()
        base = datetime(2026, 1, 1, 18, 43, tzinfo=timezone.utc)
        for second in (0, 1):
            smoother.update(parse_clock_text(f"18:43:0{second}", 0.99), base.replace(second=second))
        self.assertFalse(smoother.confirmed_start_boundary((0, 5), 3))
        smoother.update(parse_clock_text("18:43:02", 0.99), base.replace(second=2))
        self.assertTrue(smoother.confirmed_start_boundary((0, 5), 3))


if __name__ == "__main__":
    unittest.main()
