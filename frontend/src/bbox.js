export function getObjectFitContainRect(source, container) {
  if (!source.width || !source.height || !container.width || !container.height) {
    return { renderedWidth: 0, renderedHeight: 0, offsetX: 0, offsetY: 0 };
  }
  const scale = Math.min(container.width / source.width, container.height / source.height);
  const renderedWidth = source.width * scale;
  const renderedHeight = source.height * scale;
  return {
    renderedWidth,
    renderedHeight,
    offsetX: (container.width - renderedWidth) / 2,
    offsetY: (container.height - renderedHeight) / 2,
  };
}

export function bboxNormToCanvasPx(bbox, source, container) {
  const rect = getObjectFitContainRect(source, container);
  return {
    x: rect.offsetX + bbox.x1 * rect.renderedWidth,
    y: rect.offsetY + bbox.y1 * rect.renderedHeight,
    width: (bbox.x2 - bbox.x1) * rect.renderedWidth,
    height: (bbox.y2 - bbox.y1) * rect.renderedHeight,
  };
}

export function nearestTimedEvent(events, currentVideoPtsMs, toleranceMs = 500) {
  let best = null;
  let bestDelta = Infinity;
  for (const event of events) {
    if (typeof event.video_pts_ms !== "number") continue;
    const delta = Math.abs(event.video_pts_ms - currentVideoPtsMs);
    if (delta < bestDelta && delta <= toleranceMs) {
      best = event;
      bestDelta = delta;
    }
  }
  return best;
}
