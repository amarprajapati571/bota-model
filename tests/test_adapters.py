from __future__ import annotations

import unittest

from src.layout.roi import NormalizedROI
from src.publishing.webhooks import sign_webhook_payload


class AdapterTests(unittest.TestCase):
    def test_roi_converts_to_pixels(self) -> None:
        roi = NormalizedROI.from_xywh([0.1, 0.2, 0.3, 0.4])
        self.assertEqual(roi.to_pixels(1000, 500), (100, 100, 400, 300))

    def test_webhook_signature_is_deterministic(self) -> None:
        payload = {"event_type": "round.closed", "round_id": "abc"}
        self.assertEqual(sign_webhook_payload(payload, "secret"), sign_webhook_payload(payload, "secret"))
        self.assertNotEqual(sign_webhook_payload(payload, "secret"), sign_webhook_payload(payload, "other"))


if __name__ == "__main__":
    unittest.main()
