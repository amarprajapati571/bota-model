from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.live.capture import LiveCaptureService
from src.live.config import LiveConfig, load_live_config


def create_app(config: LiveConfig) -> FastAPI:
    app = FastAPI(title="Bota Live Capture Gateway")
    service = LiveCaptureService(config)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup() -> None:
        await service.start()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await service.stop()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "table_id": config.table_id}

    @app.get("/api/v1/tables/{table_id}/live-session")
    async def live_session(table_id: str) -> dict:
        return {
            "table_id": table_id,
            "stream_id": config.stream_id,
            "session_id": f"session_{table_id}_live",
            "source_video": {
                "width": config.viewport_width,
                "height": config.viewport_height,
                "fps": config.capture_fps,
            },
            "playback": config.playback,
            "realtime": {
                "protocol": "websocket",
                "ws_url": config.ws_url,
                "heartbeat_interval_ms": 5000,
            },
            "overlay_config": {
                "coordinate_space": "normalized",
                "rois": config.rois,
            },
            "current_snapshot": service.snapshot()["state"],
        }

    @app.get("/api/v1/tables/{table_id}/snapshot")
    async def snapshot(table_id: str) -> dict:
        payload = service.snapshot()
        payload["table_id"] = table_id
        return payload

    @app.websocket("/ws/v1/tables/{table_id}/live")
    async def websocket_live(websocket: WebSocket, table_id: str) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)

        def enqueue(event: dict) -> None:
            if event.get("table_id") != table_id:
                return
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                _ = queue.get_nowait()
                queue.put_nowait(event)

        service.subscribe(enqueue)
        try:
            await websocket.send_json(
                {
                    "type": "subscription.ack",
                    "table_id": table_id,
                    "stream_id": config.stream_id,
                    "latest_sequence_number": service.sequencer.value,
                }
            )
            await websocket.send_json(
                {
                    "event_type": "snapshot",
                    "table_id": table_id,
                    "stream_id": config.stream_id,
                    "sequence_number": service.sequencer.value,
                    "wall_time_ms": service.snapshot()["server_time_ms"],
                    "payload": service.snapshot()["state"],
                }
            )
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            service.unsubscribe(enqueue)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live capture and realtime gateway.")
    parser.add_argument("--config", default="configs/live/md3212.yaml")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()

    config = load_live_config(Path(args.config))
    app = create_app(config)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
