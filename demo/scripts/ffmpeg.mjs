import { spawn } from "node:child_process";
import path from "node:path";

// The Remotion compositor's FFmpeg omits the fps/setpts filters these scripts
// need, so use a full FFmpeg build from PATH (or FFMPEG_PATH/FFPROBE_PATH).
export const ffmpegPath = process.env.FFMPEG_PATH ?? "ffmpeg";
export const ffprobePath = process.env.FFPROBE_PATH ?? "ffprobe";

export const run = (command, args, { quiet = true } = {}) =>
  new Promise((resolve, reject) => {
    const child = spawn(command, args, { windowsHide: true });
    let stderr = "";
    let stdout = "";
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
      if (!quiet) process.stderr.write(chunk);
    });
    child.on("error", reject);
    child.on("exit", (code) =>
      code === 0
        ? resolve(stdout)
        : reject(
            new Error(
              `${path.basename(command)} exited ${code}: ${stderr.slice(-1500)}`,
            ),
          ),
    );
  });

export const ffmpeg = (args, options) =>
  run(
    ffmpegPath,
    ["-hide_banner", "-loglevel", "error", "-y", ...args],
    options,
  );

export const probeDuration = async (file) =>
  Number(
    (
      await run(ffprobePath, [
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        file,
      ])
    ).trim(),
  );
