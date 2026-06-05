import { bboxNormToCanvasPx } from "./bbox.js";
import { formatCard } from "./cards.js";
import { applyLiveEvent, initialState } from "./liveEvents.js";
import { buildMockEvents, liveSession as defaultLiveSession } from "./mockSession.js";

const elements = {
  tableId: document.getElementById("tableId"),
  streamId: document.getElementById("streamId"),
  streamStatus: document.getElementById("streamStatus"),
  clockText: document.getElementById("clockText"),
  roundState: document.getElementById("roundState"),
  lastEventAge: document.getElementById("lastEventAge"),
  pauseButton: document.getElementById("pauseButton"),
  debugButton: document.getElementById("debugButton"),
  videoStage: document.getElementById("videoStage"),
  liveVideo: document.getElementById("liveVideo"),
  mockVideoCanvas: document.getElementById("mockVideoCanvas"),
  overlayCanvas: document.getElementById("overlayCanvas"),
  videoMessage: document.getElementById("videoMessage"),
  protocolLabel: document.getElementById("protocolLabel"),
  latencyLabel: document.getElementById("latencyLabel"),
  recentRounds: document.getElementById("recentRounds"),
  clockMetric: document.getElementById("clockMetric"),
  confidenceMetric: document.getElementById("confidenceMetric"),
  roundMetric: document.getElementById("roundMetric"),
  roundStatusMetric: document.getElementById("roundStatusMetric"),
  playerCards: document.getElementById("playerCards"),
  bankerCards: document.getElementById("bankerCards"),
  playerTotal: document.getElementById("playerTotal"),
  bankerTotal: document.getElementById("bankerTotal"),
  winnerText: document.getElementById("winnerText"),
  reviewPanel: document.getElementById("reviewPanel"),
  reviewMessage: document.getElementById("reviewMessage"),
  eventLog: document.getElementById("eventLog"),
};

let liveSession = defaultLiveSession;
let state = { ...initialState };
let paused = false;
let debugOverlay = true;
let mockEventIndex = 0;
let animationFrame = 0;
let useMockVideo = true;
let useMockEvents = true;

async function boot() {
  liveSession = await loadLiveSession();
  useMockVideo = liveSession.demo_mode !== false;
  useMockEvents = liveSession.mock_events !== false || liveSession.realtime?.protocol === "mock";
  state = {
    ...state,
    tableId: liveSession.table_id,
    streamId: liveSession.stream_id,
  };
  elements.tableId.textContent = liveSession.table_id;
  elements.streamId.textContent = liveSession.stream_id;
  elements.protocolLabel.textContent = `${liveSession.playback.primary_protocol.toUpperCase()} playback`;
  elements.pauseButton.addEventListener("click", togglePaused);
  elements.debugButton.addEventListener("click", toggleDebug);
  window.addEventListener("resize", render);
  setupVideoPlayback();

  render();
  if (useMockEvents) {
    startMockFeed();
  } else {
    elements.eventLog.replaceChildren();
    const item = document.createElement("li");
    item.textContent = "Waiting for realtime WebSocket events";
    elements.eventLog.append(item);
  }
  startTicker();
}

async function loadLiveSession() {
  try {
    const response = await fetch("./config/live-session.json", { cache: "no-store" });
    if (!response.ok) return defaultLiveSession;
    return mergeLiveSession(defaultLiveSession, await response.json());
  } catch {
    return defaultLiveSession;
  }
}

function mergeLiveSession(base, override) {
  return {
    ...base,
    ...override,
    source_video: { ...base.source_video, ...(override.source_video ?? {}) },
    playback: { ...base.playback, ...(override.playback ?? {}) },
    realtime: { ...base.realtime, ...(override.realtime ?? {}) },
    overlay_config: {
      ...base.overlay_config,
      ...(override.overlay_config ?? {}),
      rois: {
        ...base.overlay_config.rois,
        ...(override.overlay_config?.rois ?? {}),
      },
    },
  };
}

function setupVideoPlayback() {
  const hlsUrl = liveSession.playback?.hls_url;
  if (useMockVideo || !hlsUrl) {
    elements.liveVideo.style.display = "none";
    elements.mockVideoCanvas.style.display = "block";
    return;
  }

  const video = elements.liveVideo;
  elements.mockVideoCanvas.style.display = "none";
  video.style.display = "block";
  video.controls = true;
  video.muted = true;
  elements.videoMessage.hidden = !looksLikePageUrl(hlsUrl);
  if (!elements.videoMessage.hidden) {
    elements.videoMessage.textContent =
      "This playback URL does not look like a direct HLS .m3u8 stream. If the video stays blank, use the actual playlist URL, for example https://host/path/index.m3u8.";
  }

  if (window.Hls?.isSupported()) {
    const hls = new window.Hls({
      lowLatencyMode: true,
      backBufferLength: 30,
    });
    hls.loadSource(hlsUrl);
    hls.attachMedia(video);
    hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
      elements.videoMessage.hidden = true;
      video.play().catch(() => {});
    });
    hls.on(window.Hls.Events.ERROR, (_event, data) => {
      if (data?.fatal) {
        elements.videoMessage.hidden = false;
        elements.videoMessage.textContent =
          "Video playback failed. Check that playback.hls_url is a direct .m3u8 URL and that the server allows browser/CORS access.";
      }
    });
    return;
  }

  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = hlsUrl;
    video.addEventListener("loadedmetadata", () => {
      elements.videoMessage.hidden = true;
    });
    video.addEventListener("error", () => {
      elements.videoMessage.hidden = false;
      elements.videoMessage.textContent =
        "Video playback failed. Check that playback.hls_url is a direct .m3u8 URL and that the server allows browser/CORS access.";
    });
    video.play().catch(() => {});
    return;
  }

  elements.videoMessage.hidden = false;
  elements.videoMessage.textContent =
    "HLS playback is not available. Run npm install --prefix frontend so hls.js is installed, then refresh the page.";
}

function looksLikePageUrl(url) {
  try {
    const parsed = new URL(url, window.location.href);
    return !parsed.pathname.endsWith(".m3u8") && !parsed.pathname.endsWith(".mp4");
  } catch {
    return true;
  }
}

function togglePaused() {
  paused = !paused;
  elements.pauseButton.textContent = paused ? ">" : "II";
  elements.pauseButton.classList.toggle("active", paused);
}

function toggleDebug() {
  debugOverlay = !debugOverlay;
  elements.debugButton.classList.toggle("active", debugOverlay);
  render();
}

function startMockFeed() {
  const events = buildMockEvents();
  window.setInterval(() => {
    if (paused) return;
    const event = events[mockEventIndex % events.length];
    const liveEvent = {
      ...event,
      event_id: `${event.event_id}_${Math.floor(mockEventIndex / events.length)}`,
      sequence_number: mockEventIndex + 1,
      wall_time_ms: Date.now(),
      round_id: event.round_id?.replace("1844", String(1844 + Math.floor(mockEventIndex / events.length))),
    };
    state = applyLiveEvent(state, liveEvent);
    mockEventIndex += 1;
    render();
  }, 1350);
}

function startTicker() {
  const tick = () => {
    renderMockVideo();
    renderOverlay();
    renderEventAge();
    animationFrame = window.requestAnimationFrame(tick);
  };
  animationFrame = window.requestAnimationFrame(tick);
}

function render() {
  renderHeader();
  renderRoundPanel();
  renderCardRows();
  renderRecentRounds();
  renderReview();
  renderEventLog();
  renderMockVideo();
  renderOverlay();
}

function renderHeader() {
  elements.streamStatus.textContent = state.streamStatus;
  elements.streamStatus.className = `status-pill ${state.streamStatus}`;
  elements.clockText.textContent = state.clockText ?? "--:--:--";
  elements.roundState.textContent = state.roundState;
  elements.latencyLabel.textContent = `video ${state.videoLatencyMs ?? 0}ms | ML ${state.mlLatencyMs ?? 0}ms`;
}

function renderEventAge() {
  const ageSeconds = Math.max(0, Math.round((Date.now() - state.lastEventAtMs) / 1000));
  elements.lastEventAge.textContent = `${ageSeconds}s`;
  if (ageSeconds > 20) {
    elements.streamStatus.textContent = "degraded";
    elements.streamStatus.className = "status-pill degraded";
  }
}

function renderRoundPanel() {
  elements.clockMetric.textContent = state.clockText ?? "--:--:--";
  elements.confidenceMetric.textContent = percent(state.overallConfidence ?? state.clockConfidence);
  elements.roundMetric.textContent = state.roundId ? shortRoundId(state.roundId) : "pending";
  elements.roundStatusMetric.textContent = state.roundState.replaceAll("_", " ").toLowerCase();
  elements.playerTotal.textContent = state.playerTotal ?? "-";
  elements.bankerTotal.textContent = state.bankerTotal ?? "-";
  elements.winnerText.textContent = state.winner ?? "Pending";
}

function renderCardRows() {
  renderCards(elements.playerCards, state.playerCards);
  renderCards(elements.bankerCards, state.bankerCards);
}

function renderCards(container, cards) {
  container.replaceChildren();
  const padded = [...cards];
  while (padded.length < 3) padded.push(null);

  for (const card of padded.slice(0, 3)) {
    const tile = document.createElement("div");
    tile.className = card
      ? `card-tile ${card.confidence < 0.85 ? "low" : ""}`
      : "card-tile empty-card";

    const code = document.createElement("span");
    code.className = "card-code";
    code.textContent = card ? formatCard(card.cardCode) : "-";

    const confidence = document.createElement("span");
    confidence.className = "card-confidence";
    confidence.textContent = card ? `${percent(card.confidence)} ${card.stable ? "stable" : "live"}` : "empty";

    tile.append(code, confidence);
    container.append(tile);
  }
}

function renderRecentRounds() {
  elements.recentRounds.replaceChildren();
  for (const round of state.recentRounds) {
    const row = document.createElement("tr");
    const cells = [
      round.time,
      shortRoundId(round.roundId),
      round.playerCards.map(formatCard).join(" "),
      round.bankerCards.map(formatCard).join(" "),
      `${round.playerTotal}-${round.bankerTotal}`,
      round.winner,
      percent(round.confidence),
      round.needsReview ? "Review" : "Confirmed",
    ];
    for (const value of cells) {
      const cell = document.createElement("td");
      cell.textContent = value ?? "-";
      row.append(cell);
    }
    row.lastElementChild.className = round.needsReview ? "status-review" : "status-confirmed";
    elements.recentRounds.append(row);
  }
}

function renderReview() {
  elements.reviewPanel.classList.toggle("active", state.needsReview);
  elements.reviewMessage.textContent = state.needsReview ? state.reviewReason : "Clear";
}

function renderEventLog() {
  elements.eventLog.replaceChildren();
  for (const line of state.eventLog) {
    const item = document.createElement("li");
    item.textContent = line;
    elements.eventLog.append(item);
  }
}

function renderMockVideo() {
  if (!useMockVideo) return;
  const canvas = elements.mockVideoCanvas;
  const rect = elements.videoStage.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * ratio));
  const height = Math.max(1, Math.round(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, rect.width, rect.height);

  const source = liveSession.source_video;
  const container = { width: rect.width, height: rect.height };
  const table = bboxNormToCanvasPx({ x1: 0, y1: 0, x2: 1, y2: 1 }, source, container);
  const pulse = (Math.sin(Date.now() / 750) + 1) / 2;

  ctx.fillStyle = "#050708";
  ctx.fillRect(0, 0, rect.width, rect.height);
  roundRect(ctx, table.x, table.y, table.width, table.height, 8, "#1b6c4b", "#0f3b2d");

  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.beginPath();
  ctx.ellipse(
    table.x + table.width * 0.56,
    table.y + table.height * 0.45,
    table.width * 0.34,
    table.height * 0.2,
    0,
    0,
    Math.PI * 2,
  );
  ctx.fill();

  drawZoneLabel(ctx, "PLAYER", 0.31, 0.25, source, container);
  drawZoneLabel(ctx, "BANKER", 0.58, 0.23, source, container);
  drawDigitalClock(ctx, state.clockText ?? "18:44:00", source, container, pulse);
  drawMockCards(ctx, [...state.playerCards, ...state.bankerCards], source, container);
  ctx.restore();
}

function drawDigitalClock(ctx, text, source, container, pulse) {
  const box = bboxNormToCanvasPx(liveSession.overlay_config.rois.clock, source, container);
  roundRect(ctx, box.x, box.y, box.width, box.height, 8, "#061014", "#27363b");
  ctx.fillStyle = `rgba(75, 186, 212, ${0.76 + pulse * 0.18})`;
  ctx.font = `700 ${Math.max(18, box.height * 0.22)}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, box.x + box.width / 2, box.y + box.height / 2);
}

function drawZoneLabel(ctx, label, x, y, source, container) {
  const point = bboxNormToCanvasPx({ x1: x, y1: y, x2: x, y2: y }, source, container);
  ctx.fillStyle = "rgba(239,244,246,0.68)";
  ctx.font = "700 14px Inter, system-ui, sans-serif";
  ctx.fillText(label, point.x, point.y);
}

function drawMockCards(ctx, cards, source, container) {
  for (const card of cards) {
    if (!card.bboxNorm) continue;
    const box = bboxNormToCanvasPx(card.bboxNorm, source, container);
    roundRect(ctx, box.x, box.y, box.width, box.height, 4, "#f7faf8", "#cfd8d3");
    ctx.fillStyle = card.cardCode?.endsWith("H") || card.cardCode?.endsWith("D") ? "#b71925" : "#111820";
    ctx.font = `800 ${Math.max(12, box.height * 0.22)}px ui-serif, Georgia, serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(formatCard(card.cardCode), box.x + box.width / 2, box.y + box.height / 2);
  }
}

function renderOverlay() {
  const canvas = elements.overlayCanvas;
  const rect = elements.videoStage.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * ratio));
  const height = Math.max(1, Math.round(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, rect.width, rect.height);

  const source = liveSession.source_video;
  const container = { width: rect.width, height: rect.height };
  if (debugOverlay) drawRois(ctx, source, container);
  drawCardBoxes(ctx, state.playerCards, "#31c77a", source, container);
  drawCardBoxes(ctx, state.bankerCards, "#5d8be8", source, container);
  ctx.restore();
}

function drawRois(ctx, source, container) {
  const colors = { clock: "#4bbad4", player: "#31c77a", banker: "#5d8be8" };
  for (const [name, roi] of Object.entries(liveSession.overlay_config.rois)) {
    const box = bboxNormToCanvasPx(roi, source, container);
    ctx.strokeStyle = colors[name] ?? "#eff4f6";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(box.x, box.y, box.width, box.height);
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(5,7,8,0.74)";
    ctx.fillRect(box.x + 4, box.y + 4, 64, 20);
    ctx.fillStyle = colors[name] ?? "#eff4f6";
    ctx.font = "700 12px Inter, system-ui, sans-serif";
    ctx.fillText(name.toUpperCase(), box.x + 9, box.y + 18);
  }
}

function drawCardBoxes(ctx, cards, color, source, container) {
  for (const card of cards) {
    if (!card.bboxNorm) continue;
    const box = bboxNormToCanvasPx(card.bboxNorm, source, container);
    ctx.strokeStyle = card.confidence < 0.85 ? "#e2b84b" : color;
    ctx.lineWidth = card.stable ? 3 : 1.5;
    ctx.strokeRect(box.x, box.y, box.width, box.height);
    ctx.fillStyle = "rgba(5,7,8,0.78)";
    ctx.fillRect(box.x, Math.max(0, box.y - 24), Math.max(92, box.width), 22);
    ctx.fillStyle = "#eff4f6";
    ctx.font = "700 12px Inter, system-ui, sans-serif";
    ctx.fillText(
      `${card.zone} ${card.slot} ${formatCard(card.cardCode)} ${percent(card.confidence)}`,
      box.x + 5,
      Math.max(15, box.y - 9),
    );
  }
}

function roundRect(ctx, x, y, width, height, radius, fill, stroke) {
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, radius);
  ctx.fillStyle = fill;
  ctx.fill();
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1;
    ctx.stroke();
  }
}

function percent(value) {
  if (typeof value !== "number") return "0%";
  return `${Math.round(value * 100)}%`;
}

function shortRoundId(roundId) {
  return String(roundId ?? "").replace("MD3212_", "");
}

window.addEventListener("beforeunload", () => {
  if (animationFrame) window.cancelAnimationFrame(animationFrame);
});

boot();
