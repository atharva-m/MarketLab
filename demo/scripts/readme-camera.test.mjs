import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

// Load the actual render helper without requiring Remotion, a browser or a
// TypeScript-specific Node version. TypeScript is already a locked dev dependency.
const source = await readFile(
  new URL("../src/readmeCamera.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2020,
  },
});
const {
  cameraTrack,
  pointerAt,
  contentScale,
  toStage,
  windowHeight,
  STAGE,
  WINDOW,
} = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

const timeline = (overrides = {}) => ({
  schema: "marketlab-readme-timeline-v1",
  video: "media/test.mp4",
  durationInFrames: 600,
  viewport: { width: 1440, height: 810 },
  loop: true,
  pointer: [],
  clicks: [],
  focus: [],
  typing: [],
  scrolls: [],
  chapters: [],
  urls: [],
  ...overrides,
});
const centre = { s: 1, x: STAGE.width / 2, y: STAGE.height / 2 };

test("recorded viewport coordinates align with the scaled browser content", () => {
  for (const viewport of [
    { width: 1440, height: 810 },
    { width: 1920, height: 1080 },
  ]) {
    const value = timeline({ viewport });
    assert.equal(contentScale(value) * viewport.width, WINDOW.width);
    assert.deepEqual(toStage(value, 0, 0), {
      x: WINDOW.left,
      y: WINDOW.top + WINDOW.bar,
    });
    const corner = toStage(value, viewport.width, viewport.height);
    assert.equal(corner.x, WINDOW.left + WINDOW.width);
    assert.equal(corner.y, WINDOW.top + windowHeight(value));
  }
});

test("cursor interpolation respects endpoints, fractional frames and pinned cuts", () => {
  assert.deepEqual(pointerAt([], 100), { x: 720, y: 405 });
  const points = [
    { f: 10, x: 10, y: 20 },
    { f: 20, x: 30, y: 60 },
    { f: 29.99, x: 30, y: 60 },
    { f: 30, x: 900, y: 700 },
    { f: 40, x: 1000, y: 800 },
  ];
  assert.deepEqual(pointerAt(points, 0), points[0]);
  assert.deepEqual(pointerAt(points, 100), points.at(-1));
  assert.deepEqual(pointerAt(points, 12.5), { x: 15, y: 30 });
  assert.deepEqual(pointerAt(points, 29.98), { x: 30, y: 60 });
  assert.deepEqual(pointerAt(points, 30), { x: 900, y: 700 });
});

test("idle frames settle exactly and render-worker calculations are deterministic", () => {
  const value = timeline();
  const first = cameraTrack(value, 30);
  assert.equal(first.length, value.durationInFrames);
  assert.ok(
    first.every((frame) => JSON.stringify(frame) === JSON.stringify(centre)),
  );
  assert.deepEqual(cameraTrack(value, 30), first);
});

test("click focus leads the click, holds through typing and returns to an exact resting shot", () => {
  const value = timeline({
    clicks: [{ f: 90, x: 1000, y: 400, zoom: 1.6 }],
    typing: [{ from: 100, to: 210 }],
  });
  const track = cameraTrack(value, 30);
  assert.deepEqual(track[60], centre);
  assert.ok(
    track[85].s > 1,
    "the camera must reach toward a click before the press",
  );
  assert.ok(track[190].s > 1.59, "typing keeps its input visible");
  assert.deepEqual(track.at(-1), centre);
  assert.deepEqual(cameraTrack(value, 30), track);
});

test("scroll interrupts a typing-held zoom rather than hiding moving page content", () => {
  const base = {
    clicks: [{ f: 90, x: 1200, y: 600, zoom: 1.6 }],
    typing: [{ from: 100, to: 240 }],
  };
  const held = cameraTrack(timeline(base), 30);
  const scrolling = cameraTrack(
    timeline({ ...base, scrolls: [{ from: 130, to: 180 }] }),
    30,
  );
  assert.ok(held[200].s > 1.59);
  assert.equal(scrolling[200].s, 1);
  assert.deepEqual(scrolling.at(-1), centre);
});

test("nearby clicks pan within a continuous zoom and explicit reading focus works without clicks", () => {
  const track = cameraTrack(
    timeline({
      clicks: [
        { f: 90, x: 300, y: 400 },
        { f: 120, x: 1100, y: 400 },
      ],
    }),
    30,
  );
  assert.ok(track[110].s > 1.59);
  assert.ok(track[140].s > 1.59);
  assert.ok(track[140].x > track[95].x, "the shot follows the second target");
  const reading = cameraTrack(
    timeline({
      focus: [{ from: 90, to: 240, x: 800, y: 500, zoom: 1.5 }],
    }),
    30,
  );
  assert.equal(reading[200].s, 1.5);
  assert.deepEqual(reading.at(-1), centre);
});

test("settled corner zooms stay inside the recorded browser without invalid coordinates", () => {
  for (const [x, y] of [
    [0, 0],
    [1440, 0],
    [0, 810],
    [1440, 810],
  ]) {
    const value = timeline({ focus: [{ from: 30, to: 400, x, y, zoom: 1.6 }] });
    const track = cameraTrack(value, 30);
    assert.ok(
      track.every((frame) => Object.values(frame).every(Number.isFinite)),
    );
    const shot = track[300];
    const halfWidth = STAGE.width / (2 * shot.s);
    const halfHeight = STAGE.height / (2 * shot.s);
    assert.ok(shot.x - halfWidth >= WINDOW.left - 1e-8);
    assert.ok(shot.x + halfWidth <= WINDOW.left + WINDOW.width + 1e-8);
    assert.ok(shot.y - halfHeight >= WINDOW.top - 1e-8);
    assert.ok(shot.y + halfHeight <= WINDOW.top + windowHeight(value) + 1e-8);
  }
});
