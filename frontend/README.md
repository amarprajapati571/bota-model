# Baccarat Live Frontend

Static operator dashboard for live video playback plus real-time ML state.

Start locally:

```bash
python3 -m http.server 4173 -d frontend
```

Then open `http://localhost:4173`.

Run tests:

```bash
npm test --prefix frontend
```

## What It Shows

- Live table surface with normalized ROI and card overlays.
- Stream health, clock OCR, round state, and latency.
- Player and Banker card panels.
- Winner, confidence, recent rounds, and review queue.
- Mock WebSocket-style event stream for frontend development.

## Production Integration Points

For local/manual setup, edit:

```text
frontend/config/live-session.json
```

Put the browser-safe playback URL here:

```json
{
  "demo_mode": false,
  "mock_events": false,
  "playback": {
    "primary_protocol": "hls",
    "hls_url": "http://YOUR_SERVER_IP/hls/MD3212/index.m3u8"
  }
}
```

If the provider gives only a full web page endpoint, use iframe mode:

```json
{
  "demo_mode": false,
  "mock_events": false,
  "playback": {
    "primary_protocol": "iframe",
    "iframe_url": "https://bota.dft-yui.com/",
    "fallback_protocol": "iframe"
  }
}
```

Do not put the original private casino/provider stream URL in frontend files.
If the URL is a normal website page, the video element cannot play it. Use the direct HLS playlist URL ending in `.m3u8`.

For production API setup, replace `frontend/config/live-session.json` with API data from:

```http
GET /api/v1/tables/{table_id}/live-session
GET /api/v1/tables/{table_id}/snapshot
GET /api/v1/tables/{table_id}/rounds?limit=50
```

Feed live events into `applyLiveEvent` from:

```text
wss://api.example.com/ws/v1/tables/{table_id}/live
```

Set it in `frontend/config/live-session.json`:

```json
{
  "mock_events": false,
  "realtime": {
    "protocol": "websocket",
    "ws_url": "ws://YOUR_SERVER/ws/v1/tables/MD3212/live"
  }
}
```

Without `ws_url`, the video can load but the ML data panel will remain empty.

The browser should receive signed playback URLs only. Never expose the original source stream URL.
