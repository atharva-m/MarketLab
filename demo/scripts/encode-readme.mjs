// Encodes a rendered README master for GitHub.
// Usage:
//   node scripts/encode-readme.mjs gif <master.mp4> <out.gif> [--no-limit]
//   node scripts/encode-readme.mjs mp4 <master.mp4> <out.mp4>
// By default output fits GitHub's 10 MB attachment upload. --no-limit makes a
// higher-quality GIF for committing to the repository instead.
import { mkdtemp, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { ffmpeg, probeDuration } from "./ffmpeg.mjs";

const [kind, masterArg, outputArg, option] = process.argv.slice(2);
if (!["gif", "mp4"].includes(kind) || !masterArg || !outputArg)
  throw new Error(
    "Usage: encode-readme.mjs gif|mp4 <master.mp4> <output> [--no-limit]",
  );
const master = path.resolve(masterArg);
const output = path.resolve(outputArg);
const unlimited = option === "--no-limit";
// GitHub caps attachment images/GIFs and free-plan videos at 10 MB; keep a
// decimal margin below it.
const limit = unlimited ? Infinity : 9.5e6;
const work = await mkdtemp(path.join(os.tmpdir(), "readme-encode-"));
const megabytes = async (file) => (await stat(file)).size / 1024 / 1024;

try {
  if (kind === "gif") {
    // Largest first. No dithering: the flat UI compresses far better, and
    // README images display at roughly 900-1000 px wide anyway.
    const presets = [
      ...(unlimited ? [{ width: 1200, fps: 15, colors: 256 }] : []),
      { width: 1100, fps: 15, colors: 192 },
      { width: 1000, fps: 15, colors: 160 },
      { width: 1000, fps: 12, colors: 160 },
      { width: 960, fps: 12, colors: 128 },
      { width: 900, fps: 12, colors: 128 },
      { width: 840, fps: 10, colors: 112 },
    ];
    for (const preset of presets) {
      const palette = path.join(work, "palette.png");
      const filters = `fps=${preset.fps},scale=${preset.width}:-1:flags=lanczos`;
      await ffmpeg([
        "-i",
        master,
        "-vf",
        `${filters},palettegen=max_colors=${preset.colors}`,
        palette,
      ]);
      await ffmpeg([
        "-i",
        master,
        "-i",
        palette,
        "-lavfi",
        `${filters}[x];[x][1:v]paletteuse=dither=none:diff_mode=rectangle`,
        "-loop",
        "0",
        output,
      ]);
      const size = await megabytes(output);
      console.log(
        JSON.stringify({ ...preset, megabytes: Number(size.toFixed(2)) }),
      );
      if (size * 1024 * 1024 <= limit) break;
      if (preset === presets[presets.length - 1])
        throw new Error("GIF still exceeds the attachment limit");
    }
  } else {
    // Two-pass H.264 sized just under the limit; no audio track.
    const seconds = await probeDuration(master);
    let bitrate = Math.floor(((limit * 8) / seconds) * 0.95);
    for (let attempt = 0; attempt < 4; attempt++) {
      const log = path.join(work, "pass");
      const common = [
        "-i",
        master,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-b:v",
        String(bitrate),
        "-x264-params",
        "aq-mode=3",
        "-passlogfile",
        log,
      ];
      await ffmpeg([
        ...common,
        "-pass",
        "1",
        "-f",
        "mp4",
        os.platform() === "win32" ? "NUL" : "/dev/null",
      ]);
      await ffmpeg([
        ...common,
        "-pass",
        "2",
        "-movflags",
        "+faststart",
        output,
      ]);
      const size = await megabytes(output);
      console.log(
        JSON.stringify({
          seconds,
          bitrate,
          megabytes: Number(size.toFixed(2)),
        }),
      );
      if (size * 1024 * 1024 <= limit) break;
      bitrate = Math.floor(bitrate * 0.92);
      if (attempt === 3)
        throw new Error("MP4 still exceeds the attachment limit");
    }
  }
} finally {
  await rm(work, { recursive: true, force: true });
}
