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

Replace `frontend/src/mockSession.js` with API data from:

```http
GET /api/v1/tables/{table_id}/live-session
GET /api/v1/tables/{table_id}/snapshot
GET /api/v1/tables/{table_id}/rounds?limit=50
```

Feed live events into `applyLiveEvent` from:

```text
wss://api.example.com/ws/v1/tables/{table_id}/live
```

The browser should receive signed playback URLs only. Never expose the original source stream URL.
