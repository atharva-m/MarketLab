import type { Point, ReadmeTimeline } from "./readmeTypes";

// Stage geometry: a 1920x1080 canvas holding a browser window whose content
// area shows the recorded viewport scaled to 1520 px wide, leaving room below
// for captions.
export const STAGE = { width: 1920, height: 1080 };
export const WINDOW = { left: 200, top: 40, width: 1520, bar: 40 };

export const contentScale = (timeline: ReadmeTimeline) =>
  WINDOW.width / timeline.viewport.width;

export const windowHeight = (timeline: ReadmeTimeline) =>
  WINDOW.bar + timeline.viewport.height * contentScale(timeline);

export const toStage = (timeline: ReadmeTimeline, x: number, y: number) => {
  const k = contentScale(timeline);
  return { x: WINDOW.left + x * k, y: WINDOW.top + WINDOW.bar + y * k };
};

export const pointerAt = (pointer: Point[], f: number) => {
  if (!pointer.length) return { x: 720, y: 405 };
  if (f <= pointer[0].f) return pointer[0];
  let lo = 0;
  let hi = pointer.length - 1;
  if (f >= pointer[hi].f) return pointer[hi];
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (pointer[mid].f <= f) lo = mid;
    else hi = mid;
  }
  const a = pointer[lo];
  const b = pointer[hi];
  const p = b.f === a.f ? 1 : (f - a.f) / (b.f - a.f);
  return { x: a.x + (b.x - a.x) * p, y: a.y + (b.y - a.y) * p };
};

type Group = { start: number; end: number; zoom: number; points: Point[] };

// Clicks close together share one zoomed shot that pans between them; typing
// right after a click keeps the shot until the typing ends.
const focusGroups = (timeline: ReadmeTimeline, fps: number): Group[] => {
  const groups: Group[] = [];
  const clicks = timeline.clicks.slice().sort((a, b) => a.f - b.f);
  for (const click of clicks) {
    let end = click.f + 1.0 * fps;
    for (const typing of timeline.typing)
      if (typing.from >= click.f && typing.from - click.f < 0.8 * fps)
        end = Math.max(end, typing.to + 0.6 * fps);
    const last = groups[groups.length - 1];
    const scrolled =
      last &&
      timeline.scrolls.some((s) => s.from > last.end - fps && s.from < click.f);
    if (last && !scrolled && click.f - last.end < 0.9 * fps) {
      last.end = Math.max(last.end, end);
      last.points.push(click);
      last.zoom = Math.max(last.zoom, click.zoom ?? 1.6);
    } else {
      groups.push({
        start: click.f,
        end,
        zoom: click.zoom ?? 1.6,
        points: [click],
      });
    }
  }
  // A scroll ends a zoomed shot early so the page motion stays legible.
  for (const group of groups)
    for (const s of timeline.scrolls)
      if (s.from > group.start && s.from < group.end) group.end = s.from;
  for (const focus of timeline.focus)
    groups.push({
      start: focus.from,
      end: focus.to,
      zoom: focus.zoom,
      points: [{ f: focus.from, x: focus.x, y: focus.y }],
    });
  return groups.sort((a, b) => a.start - b.start);
};

// Critically damped approach; it snaps once within `settle` so a resting shot
// renders identical frames instead of endless sub-pixel drift (which would
// defeat GIF frame differencing and waste video bitrate).
const smoothDamp = (
  current: number,
  target: number,
  velocity: number,
  smoothTime: number,
  dt: number,
  settle: number,
) => {
  const omega = 2 / smoothTime;
  const x = omega * dt;
  const exp = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  const change = current - target;
  const temp = (velocity + omega * change) * dt;
  const nextVelocity = (velocity - omega * temp) * exp;
  const value = target + (change + temp) * exp;
  if (Math.abs(value - target) < settle && Math.abs(nextVelocity) < settle * 8)
    return { value: target, velocity: 0 };
  return { value, velocity: nextVelocity };
};

const clampCenter = (
  timeline: ReadmeTimeline,
  s: number,
  x: number,
  y: number,
) => {
  // Zoomed shots stay inside the browser window once it fills the frame.
  const blend = Math.min(1, Math.max(0, (s - 1) / 0.25));
  const left = WINDOW.left * blend;
  const top = WINDOW.top * blend;
  const right =
    STAGE.width - (STAGE.width - WINDOW.left - WINDOW.width) * blend;
  const bottom =
    STAGE.height - (STAGE.height - WINDOW.top - windowHeight(timeline)) * blend;
  const hw = STAGE.width / 2 / s;
  const hh = STAGE.height / 2 / s;
  const cx =
    right - left <= 2 * hw
      ? (left + right) / 2
      : Math.min(right - hw, Math.max(left + hw, x));
  const cy =
    bottom - top <= 2 * hh
      ? (top + bottom) / 2
      : Math.min(bottom - hh, Math.max(top + hh, y));
  return { x: cx, y: cy };
};

export type Camera = { s: number; x: number; y: number };

// Per-frame camera, simulated from frame 0 so every render worker agrees.
export const cameraTrack = (
  timeline: ReadmeTimeline,
  fps: number,
): Camera[] => {
  const groups = focusGroups(timeline, fps);
  const lead = 0.55 * fps;
  const centre = { x: STAGE.width / 2, y: STAGE.height / 2 };
  const target = (f: number): Camera => {
    for (const group of groups) {
      if (f < group.start - lead || f > group.end) continue;
      // Hold each click briefly, then pan toward the next one.
      const points = group.points;
      let focus = points[points.length - 1];
      for (const point of points)
        if (point.f > f - 0.2 * fps) {
          focus = point;
          break;
        }
      const stage = toStage(timeline, focus.x, focus.y);
      return {
        s: group.zoom,
        ...clampCenter(timeline, group.zoom, stage.x, stage.y),
      };
    }
    return { s: 1, ...centre };
  };
  const dt = 1 / fps;
  const track: Camera[] = [];
  let s = { value: 1, velocity: 0 };
  let x = { value: centre.x, velocity: 0 };
  let y = { value: centre.y, velocity: 0 };
  for (let f = 0; f < timeline.durationInFrames; f++) {
    const goal = target(f);
    s = smoothDamp(s.value, goal.s, s.velocity, 0.3, dt, 0.0006);
    x = smoothDamp(x.value, goal.x, x.velocity, 0.34, dt, 0.35);
    y = smoothDamp(y.value, goal.y, y.velocity, 0.34, dt, 0.35);
    track.push({
      s: s.value,
      ...clampCenter(timeline, s.value, x.value, y.value),
    });
  }
  return track;
};
