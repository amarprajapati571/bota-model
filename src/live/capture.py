from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Callable

from src.live.config import LiveConfig
from src.live.events import EventSequencer, make_event, review_required_event, stream_health_event
from src.live.pipeline import LiveInferencePipeline


EventCallback = Callable[[dict], None]


@dataclass
class CaptureState:
    connected: bool = False
    last_frame_id: str | None = None
    last_frame_at: datetime | None = None
    last_frame_path: Path | None = None
    frame_count: int = 0
    last_player_cards: list[dict] | None = None
    last_banker_cards: list[dict] | None = None
    last_clock: dict | None = None
    last_round_state: str | None = None
    last_debug: dict | None = None
    error: str | None = None


class LiveCaptureService:
    def __init__(self, config: LiveConfig) -> None:
        self.config = config
        self.state = CaptureState()
        self.sequencer = EventSequencer()
        self.pipeline = LiveInferencePipeline(
            config,
            self.sequencer,
            card_hold_frames=config.card_hold_frames,
            card_confirm_frames=config.card_confirm_frames,
            debug_sample_every=config.debug_sample_every,
        )
        self._subscribers: set[EventCallback] = set()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def subscribe(self, callback: EventCallback) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        self._subscribers.discard(callback)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self.config.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="live-capture-service")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    def snapshot(self) -> dict:
        return {
            "table_id": self.config.table_id,
            "stream_id": self.config.stream_id,
            "server_time_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            "latest_sequence_number": self.sequencer.value,
            "state": {
                "stream_status": "healthy" if self.state.connected else "degraded",
                "round_id": None,
                "round_state": "CAPTURING_FRAMES" if self.state.connected else "WAITING_FOR_STREAM",
                "clock_text": self.state.last_clock.get("clock_text") if self.state.last_clock else None,
                "player_cards": [],
                "banker_cards": [],
                "winner": None,
                "overall_confidence": None,
                "needs_review": True,
                "last_frame_id": self.state.last_frame_id,
                "last_frame_path": str(self.state.last_frame_path) if self.state.last_frame_path else None,
                "last_player_cards": self.state.last_player_cards or [],
                "last_banker_cards": self.state.last_banker_cards or [],
                "last_clock": self.state.last_clock,
                "last_round_state": self.state.last_round_state,
                "last_debug": self.state.last_debug,
                "error": self.state.error,
            },
        }

    async def _run(self) -> None:
        if self.config.source_type != "browser_page":
            self.state.error = f"Unsupported live source type: {self.config.source_type}"
            self._publish_review(self.state.error)
            return

        try:
            await self._run_browser_page_capture()
        except Exception as exc:  # noqa: BLE001 - published to operator UI.
            self.state.connected = False
            self.state.error = str(exc)
            self._publish_review(f"Live capture failed: {exc}", "LIVE_CAPTURE_FAILED")

    async def _run_browser_page_capture(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: python3 -m pip install -r requirements.txt "
                "and python3 -m playwright install chromium"
            ) from exc

        interval_seconds = 1.0 / max(self.config.capture_fps, 0.1)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                }
            )
            await page.goto(self.config.source_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(self.config.wait_after_load_ms)
            self.state.connected = True
            self._publish_health()
            self._publish_review(
                "Live frames are being captured. Card boxes and timer metadata are active. "
                "Rank/suit classification still requires a configured model before winner confirmation.",
            )

            while not self._stop.is_set():
                started = datetime.now(timezone.utc)
                image_bytes = await page.screenshot(type="jpeg", quality=85, full_page=False)
                self._handle_frame(image_bytes, started)
                self._publish_health()
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                await asyncio.sleep(max(0.0, interval_seconds - elapsed))

            await browser.close()

    def _handle_frame(self, image_bytes: bytes, captured_at: datetime) -> None:
        self.state.frame_count += 1
        frame_id = f"{self.config.table_id}-{captured_at.strftime('%Y%m%dT%H%M%S')}-{self.state.frame_count:06d}"
        frame_path = self.config.evidence_dir / "latest.jpg"
        if self.config.save_latest_frame:
            frame_path.write_bytes(image_bytes)
        if self.config.save_roi_crops:
            self._save_roi_crops(image_bytes)

        self.state.last_frame_id = frame_id
        self.state.last_frame_at = captured_at
        self.state.last_frame_path = frame_path
        self.state.error = None
        result = self.pipeline.process_frame(
            image_bytes,
            captured_at,
            frame_id,
            self.state.frame_count,
        )
        self.state.last_player_cards = result.card_payload["player_cards"]
        self.state.last_banker_cards = result.card_payload["banker_cards"]
        self.state.last_clock = result.clock.to_event_payload()
        self.state.last_round_state = result.round_state
        self.state.last_debug = {
            "frame_id": result.debug_payload.get("frame_id"),
            "image": result.debug_payload.get("image"),
            "rois": result.debug_payload.get("rois"),
            "identity_status": result.debug_payload.get("identity_status"),
        }

        self._publish(
            make_event(
                "frame.captured",
                self.config.table_id,
                self.config.stream_id,
                self.sequencer.next(),
                {
                    "frame_id": frame_id,
                    "frame_uri": str(frame_path),
                    "roi_crops_saved": self.config.save_roi_crops,
                    "debug_artifacts_dir": str(self.config.evidence_dir / "debug"),
                    "model_outputs_available": True,
                    "identity_status": "boxes_only",
                    "processing_ms": result.processing_ms,
                    "round_state": result.round_state,
                },
                frame_id=frame_id,
            )
        )
        for event in result.events:
            self._publish(event)

    def _save_roi_crops(self, image_bytes: bytes) -> None:
        try:
            from PIL import Image
        except ImportError:
            return

        crop_dir = self.config.evidence_dir / "rois"
        crop_dir.mkdir(parents=True, exist_ok=True)
        image = Image.open(BytesIO(image_bytes))
        width, height = image.size
        for name, roi in self.config.rois.items():
            left = int(float(roi["x1"]) * width)
            top = int(float(roi["y1"]) * height)
            right = int(float(roi["x2"]) * width)
            bottom = int(float(roi["y2"]) * height)
            image.crop((left, top, right, bottom)).save(crop_dir / f"{name}.jpg", quality=90)

    def _publish_health(self) -> None:
        age_ms = 0
        if self.state.last_frame_at:
            age_ms = int((datetime.now(timezone.utc) - self.state.last_frame_at).total_seconds() * 1000)
        self._publish(
            stream_health_event(
                self.config.table_id,
                self.config.stream_id,
                self.sequencer.next(),
                status="healthy" if self.state.connected else "degraded",
                source_connected=self.state.connected,
                last_frame_age_ms=age_ms,
                capture_fps=self.config.capture_fps,
            )
        )

    def _publish_review(self, message: str, reason_code: str = "ML_MODELS_NOT_CONFIGURED") -> None:
        self._publish(
            review_required_event(
                self.config.table_id,
                self.config.stream_id,
                self.sequencer.next(),
                message=message,
                reason_code=reason_code,
            )
        )

    def _publish(self, event: dict) -> None:
        for callback in tuple(self._subscribers):
            callback(event)
