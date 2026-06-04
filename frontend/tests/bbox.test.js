import test from "node:test";
import assert from "node:assert/strict";

import { bboxNormToCanvasPx, getObjectFitContainRect, nearestTimedEvent } from "../src/bbox.js";

test("object-fit contain rect preserves aspect ratio with letterboxing", () => {
  const rect = getObjectFitContainRect(
    { width: 1466, height: 746 },
    { width: 1000, height: 600 },
  );
  assert.equal(Math.round(rect.renderedWidth), 1000);
  assert.equal(Math.round(rect.renderedHeight), 509);
  assert.equal(Math.round(rect.offsetX), 0);
  assert.equal(Math.round(rect.offsetY), 46);
});

test("normalized bbox maps into rendered canvas coordinates", () => {
  const box = bboxNormToCanvasPx(
    { x1: 0.1, y1: 0.2, x2: 0.3, y2: 0.4 },
    { width: 1000, height: 500 },
    { width: 500, height: 500 },
  );
  assert.equal(box.x, 50);
  assert.equal(box.y, 175);
  assert.equal(Math.round(box.width), 100);
  assert.equal(box.height, 50);
});

test("nearest timed event respects tolerance", () => {
  const events = [
    { sequence_number: 1, video_pts_ms: 1000 },
    { sequence_number: 2, video_pts_ms: 1600 },
  ];
  assert.equal(nearestTimedEvent(events, 1550, 100)?.sequence_number, 2);
  assert.equal(nearestTimedEvent(events, 1900, 100), null);
});
