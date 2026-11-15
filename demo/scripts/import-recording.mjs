// Wraps a plain screen recording of the workspace as a capture directory for
// prepare-readme.mjs, for footage that capture-workflow.mjs did not record.
// The recording keeps its own cursor, so no pointer log is produced and the
// composition draws none.
//
// Usage: node scripts/import-recording.mjs <video> <events.json> <fresh capture dir> [--crop=<w>:<h>:<x>:<y>]
// events.json is [{ "t": <seconds from the first frame>, "event": "<name>" }]
// and must contain "record-end". --crop keeps one region of the frame; cut
// list coordinates are then relative to that region.
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { ffmpeg } from "./ffmpeg.mjs";

const [videoArg, eventsArg, outArg, cropArg] = process.argv.slice(2);
const crop = /^--crop=(\d+):(\d+):(\d+):(\d+)$/.exec(cropArg ?? "");
if (!videoArg || !eventsArg || !outArg || (cropArg && !crop))
  throw new Error(
    "Usage: import-recording.mjs <video> <events.json> <capture dir> [--crop=<w>:<h>:<x>:<y>]",
  );
if (!crop) throw new Error("Pass --crop=<w>:<h>:<x>:<y> for the page region");
const [width, height, x, y] = crop.slice(1).map(Number);
const out = path.resolve(outArg);
await mkdir(out, { recursive: false });
const events = JSON.parse(
  (await readFile(path.resolve(eventsArg), "utf8")).replace(/^﻿/, ""),
)
  .filter((e) => e.t >= 0)
  .map((e) => ({ t: Math.round(e.t * 1000), type: e.event }));
if (!events.some((e) => e.type === "record-end"))
  throw new Error("events.json has no record-end");
await ffmpeg([
  "-i",
  path.resolve(videoArg),
  "-vf",
  `crop=${width}:${height}:${x}:${y},fps=30,format=yuv420p`,
  "-c:v",
  "libx264",
  "-preset",
  "medium",
  "-crf",
  "12",
  "-an",
  path.join(out, "source.mp4"),
]);
await writeFile(
  path.join(out, "capture.json"),
  JSON.stringify(
    {
      schema: "marketlab-recording-v1",
      status: "passed",
      viewport: { width, height },
      cursor: "recorded",
      frames: [{ file: null, t: 0 }],
      pointer: [],
      events,
      errors: [],
    },
    null,
    1,
  ),
);
console.log(
  JSON.stringify({ capture: out, width, height, events: events.length }),
);
