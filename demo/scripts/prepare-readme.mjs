// Turns a capture from capture-workflow.mjs into an edited screen video plus a
// frame-accurate timeline (pointer, clicks, typing, scrolls, chapters) for
// the ReadmeHero/ReadmeHighlight compositions.
//
// Usage: node scripts/prepare-readme.mjs <capture dir> <cut.json> <props.json>
// Cut times are seconds since the first captured frame.
import { copyFile, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { ffmpeg } from "./ffmpeg.mjs";

const [captureArg, cutArg, propsArg] = process.argv.slice(2);
if (!captureArg || !cutArg || !propsArg)
  throw new Error(
    "Usage: prepare-readme.mjs <capture dir> <cut.json> <props.json>",
  );
const captureDir = path.resolve(captureArg);
const capture = JSON.parse(
  await readFile(path.join(captureDir, "capture.json"), "utf8"),
);
const cut = JSON.parse(await readFile(path.resolve(cutArg), "utf8"));
if (capture.status !== "passed") throw new Error("Capture did not pass");
if (!/^[a-z0-9-]+$/.test(cut.id)) throw new Error("Cut id must be lowercase");
const fps = 30;
const origin = capture.frames[0].t;
const sec = (t) => (t - origin) / 1000;
const end = sec(capture.events.find((e) => e.type === "record-end").t) + 0.5;

// 1. Variable-rate screencast frames -> one constant-rate source video.
const source = path.join(captureDir, "source.mp4");
try {
  await stat(source);
} catch {
  const lines = [];
  capture.frames.forEach((frame, i) => {
    const next =
      i + 1 < capture.frames.length ? sec(capture.frames[i + 1].t) : end;
    lines.push(
      `file '${frame.file}'`,
      `duration ${(next - sec(frame.t)).toFixed(4)}`,
    );
  });
  lines.push(`file '${capture.frames[capture.frames.length - 1].file}'`);
  const list = path.join(captureDir, "frames.txt");
  await writeFile(list, lines.join("\n"));
  console.log("Encoding constant-rate source video…");
  await ffmpeg([
    "-f",
    "concat",
    "-safe",
    "0",
    "-i",
    list,
    "-vf",
    `fps=${fps},format=yuv420p`,
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "12",
    source,
  ]);
}

// 2. Segments: whole output frames, so the event mapping stays exact.
let cursor = 0;
const segments = cut.segments.map((s) => {
  const frames = Math.max(
    1,
    Math.round(((s.to - s.from) / (s.speed ?? 1)) * fps),
  );
  const segment = {
    ...s,
    start: cursor,
    frames,
    speed: ((s.to - s.from) * fps) / frames,
  };
  cursor += frames;
  return segment;
});
const durationInFrames = cursor;
const map = (c) => {
  for (const s of segments)
    if (c >= s.from && c < s.to)
      return s.start + ((c - s.from) * fps) / s.speed;
  return null;
};
// Times inside a removed gap land on the start of the next kept segment.
const mapClamp = (c) => {
  const direct = map(c);
  if (direct !== null) return direct;
  const next = segments.find((s) => s.from >= c);
  return next ? next.start : durationInFrames - 1;
};

const screen = `readme-${cut.id}-screen.mp4`;
const media = path.resolve("public", "media");
await mkdir(media, { recursive: true });
const edited = path.join(captureDir, screen);
const inputs = [];
const chains = [];
segments.forEach((s, i) => {
  inputs.push(
    "-ss",
    s.from.toFixed(3),
    "-t",
    (s.to - s.from + 0.1).toFixed(3),
    "-i",
    source,
  );
  chains.push(
    `[${i}:v]setpts=(PTS-STARTPTS)/${s.speed.toFixed(6)},fps=${fps},trim=end_frame=${s.frames},setpts=PTS-STARTPTS[v${i}]`,
  );
});
const graph = `${chains.join(";")};${segments.map((_, i) => `[v${i}]`).join("")}concat=n=${segments.length}:v=1:a=0,format=yuv420p[out]`;
console.log(
  `Cutting ${segments.length} segments into ${durationInFrames} frames…`,
);
await ffmpeg([
  ...inputs,
  "-filter_complex",
  graph,
  "-map",
  "[out]",
  "-c:v",
  "libx264",
  "-preset",
  "medium",
  "-crf",
  "12",
  "-r",
  String(fps),
  edited,
]);
await copyFile(edited, path.join(media, screen));

// 3. Map the interaction log onto output frames.
const positionAt = (c) => {
  let last = capture.pointer[0] ?? { x: 760, y: 470 };
  for (const p of capture.pointer) if (sec(p.t) <= c) last = p;
  return { x: last.x, y: last.y };
};
const pointer = [];
for (const p of capture.pointer) {
  const f = map(sec(p.t));
  if (f !== null) pointer.push({ f, x: p.x, y: p.y });
}
// Pin the pointer at each cut so interpolation never glides across a gap.
for (const s of segments) {
  pointer.push({ f: s.start, ...positionAt(s.from) });
  pointer.push({ f: s.start + s.frames - 0.01, ...positionAt(s.to) });
}
pointer.sort((a, b) => a.f - b.f);

const events = capture.events.map((e) => ({ ...e, c: sec(e.t) }));
const downs = events.filter((e) => e.type === "down");
const clicks = [];
downs.forEach((e, index) => {
  const f = map(e.c);
  const zoom = cut.clickZoom?.[String(index)] ?? cut.zoom ?? 1.6;
  if (f !== null && zoom !== 0) clicks.push({ f, x: e.x, y: e.y, zoom });
});
const pairs = (open, close) => {
  const out = [];
  events.forEach((e, i) => {
    if (e.type !== open) return;
    const finish = events.slice(i + 1).find((x) => x.type === close);
    if (!finish || (map(e.c) === null && map(finish.c) === null)) return;
    out.push({ from: mapClamp(e.c), to: mapClamp(finish.c), event: e, finish });
  });
  return out;
};
const typing = pairs("type-start", "type-end").map(({ from, to }) => ({
  from,
  to,
}));
const scrolls = pairs("scroll-start", "scroll-end").map(({ from, to }) => ({
  from,
  to,
}));
const focus = (cut.focus ?? []).map((f) => ({
  from: mapClamp(f.from),
  to: mapClamp(f.to),
  x: f.x,
  y: f.y,
  zoom: f.zoom ?? 1.5,
}));
// A caption ends at the next chapter, its `until`, or after captionSeconds.
const chapters = (cut.chapters ?? []).map((chapter, i, all) => {
  const from = Math.round(mapClamp(chapter.at));
  const to = Math.round(
    chapter.until !== undefined
      ? mapClamp(chapter.until)
      : i + 1 < all.length
        ? mapClamp(all[i + 1].at) - 4
        : durationInFrames - 2,
  );
  const cap = cut.captionSeconds
    ? from + Math.round(cut.captionSeconds * fps)
    : to;
  return { from, to: Math.min(to, cap), label: chapter.label };
});
const navs = events.filter((e) => e.type === "nav");
const urls = [];
const opening = navs.filter((e) => e.c <= segments[0].from).pop() ?? navs[0];
if (opening) urls.push({ f: 0, url: opening.url });
for (const e of navs) {
  const f = map(e.c);
  if (f !== null) urls.push({ f, url: e.url });
}

const timeline = {
  schema: "marketlab-readme-timeline-v1",
  video: `media/${screen}`,
  durationInFrames,
  viewport: capture.viewport,
  loop: Boolean(cut.loop),
  pointer,
  clicks,
  focus,
  typing,
  scrolls,
  chapters,
  urls,
};
await writeFile(path.resolve(propsArg), JSON.stringify({ timeline }, null, 1));
console.log(
  JSON.stringify({
    id: cut.id,
    seconds: durationInFrames / fps,
    frames: durationInFrames,
    clicks: clicks.length,
    video: timeline.video,
  }),
);
