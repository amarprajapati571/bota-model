# Frontend Streaming

The frontend uses two independent channels:

- Video playback: WebRTC primary, HLS fallback.
- ML data: WebSocket primary, REST snapshot/backfill fallback.

The static implementation in `frontend/` is a dependency-free operator dashboard that mirrors the intended production contract. It uses a mock event source until a realtime gateway exists.

## Local Stream Configuration

Edit:

```text
frontend/config/live-session.json
```

For demo mode:

```json
{
  "demo_mode": true
}
```

For real HLS playback:

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

For a provider page endpoint instead of HLS:

```json
{
  "demo_mode": false,
  "mock_events": false,
  "playback": {
    "primary_protocol": "iframe",
    "iframe_url": "https://bota.dft-yui.com/"
  }
}
```

Only put the public/signed playback URL here. The original source stream URL belongs on the backend ingest/FFmpeg side.
For HLS playback, the URL should normally end with `.m3u8`.

## State Flow

1. Load live-session configuration.
2. Start playback using the signed media URL.
3. Subscribe to live events.
4. Deduplicate by `event_id`.
5. Ignore stale `sequence_number` values.
6. Apply events through the reducer.
7. Draw normalized ROI/card boxes on the canvas overlay.
8. Update recent rounds and review queue from final/review events.

## Event Types

Supported now:

- `stream.health`
- `clock.tick`
- `round.state`
- `cards.detected`
- `round.final`
- `review.required`

## Overlay Coordinates

All boxes are normalized `{ x1, y1, x2, y2 }` in source video space. The helper in `frontend/src/bbox.js` maps them to the rendered canvas while accounting for `object-fit: contain` letterboxing.

## Next Production Steps

- Replace mock event timer with an authenticated WebSocket client.
- Fetch signed playback URLs from the REST API.
- Add HLS/WebRTC player adapters.
- Add snapshot recovery after reconnect.
- Add review correction page and API calls.
- Add browser telemetry for disconnects, video errors, and stale data.
