import assert from "node:assert/strict";
import http from "node:http";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { createReadStream } from "node:fs";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  openBrowser,
  getVideoMetadata,
  RenderInternals,
} from "@remotion/renderer";
import { hashFile } from "./manifest.mjs";
import { withReviewSession } from "./review-session.mjs";

// Review the encoded artifact, rather than rerendering the composition for QA.
// Native FFmpeg decoding provides independent native frame verification.
const [videoFile, outputDirectory, priorPlaybackFile] = process.argv.slice(2);
const runNative = promisify(execFile);
if (!videoFile || !outputDirectory)
  throw new Error(
    "Usage: node --require ./scripts/local-only.cjs scripts/review.mjs final.mp4 fresh-review-directory [passed-playback.json]",
  );
const actualFile = path.resolve(videoFile);
const file = await stat(actualFile);
if (!file.isFile()) throw new Error("Expected encoded local video");
const metadata = await getVideoMetadata(actualFile);
assert.equal(metadata.width, 1920);
assert.equal(metadata.height, 1080);
assert.ok(Math.abs(metadata.durationInSeconds - 180) < 0.1);
await mkdir(outputDirectory, { recursive: false });
const receipt = {
  schema: "marketlab-demo-playback-v1",
  status: "running",
  outputSha256: await hashFile(actualFile),
  qaSourceHashes: Object.fromEntries(
    await Promise.all(
      [
        "scripts/review.mjs",
        "scripts/review-session.mjs",
        "scripts/local-only.cjs",
      ].map(async (file) => [file, await hashFile(file)]),
    ),
  ),
  metadata,
  observations: [],
  decodedFrames: [],
  contactSheets: [],
  visualReview:
    "pending; inspect every-second contact sheets and full-resolution chapter/caption frames",
  limitations:
    "Full browser playback plus every-second and boundary frame extraction do not constitute manual continuous viewing or semantic inspection of every encoded frame.",
};
if (priorPlaybackFile) {
  const prior = JSON.parse(await readFile(priorPlaybackFile, "utf8"));
  assert.equal(prior.status, "passed");
  assert.equal(prior.outputSha256, receipt.outputSha256);
  assert.equal(prior.resourcesClosed, true);
  assert.equal(prior.observations.at(-1).ended, true);
  assert.ok(prior.observations.at(-1).currentTime >= 179.9);
  assert.ok(prior.observations.every((entry) => !entry.error));
  receipt.priorPlayback = {
    file: path.resolve(priorPlaybackFile),
    sha256: await hashFile(priorPlaybackFile),
  };
}
const flush = async () =>
  writeFile(
    path.join(outputDirectory, "playback.json"),
    JSON.stringify(receipt, null, 2),
  );
await flush();
const server = http.createServer((request, response) => {
  if (request.url === "/") {
    response.setHeader("Content-Type", "text/html");
    response.end(
      '<!doctype html><html><body style="margin:0;background:#000"><video id="review" src="/video" muted playsinline style="width:1920px;height:1080px"></video></body></html>',
    );
    return;
  }
  if (request.url !== "/video") {
    response.writeHead(404).end();
    return;
  }
  const range = request.headers.range;
  let start = 0;
  let end = file.size - 1;
  if (range) {
    const match = /^bytes=(\d+)-(\d*)$/.exec(range);
    if (!match) {
      response.writeHead(416).end();
      return;
    }
    start = Number(match[1]);
    end = match[2] ? Number(match[2]) : end;
    if (start > end || end >= file.size) {
      response.writeHead(416).end();
      return;
    }
  }
  response.writeHead(range ? 206 : 200, {
    "Content-Type": "video/mp4",
    "Accept-Ranges": "bytes",
    "Content-Length": end - start + 1,
    ...(range ? { "Content-Range": `bytes ${start}-${end}/${file.size}` } : {}),
  });
  const stream = createReadStream(actualFile, { start, end });
  response.on("close", () => stream.destroy());
  stream.on("error", () => response.destroy());
  stream.pipe(response);
});
const began = performance.now();
await withReviewSession({
  server,
  launch: () => openBrowser("chrome"),
  run: async (browser, address) => {
    assert.equal(address.address, "127.0.0.1");
    const page = await browser.newPage({
      context: () => null,
      logLevel: "warn",
      indent: false,
      pageIndex: 0,
      onBrowserLog: null,
      onLog: () => {},
    });
    await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
    await page.goto({
      url: `http://127.0.0.1:${address.port}/`,
      timeout: 10000,
    });
    if (!priorPlaybackFile) {
      await page.evaluate(async () => {
        const video = document.getElementById("review");
        await video.play();
      });
      while (performance.now() - began < 240000) {
        const observation = await page.evaluate(() => {
          const video = document.getElementById("review");
          const quality = video.getVideoPlaybackQuality();
          return {
            currentTime: video.currentTime,
            ended: video.ended,
            paused: video.paused,
            readyState: video.readyState,
            error: video.error
              ? { code: video.error.code, message: video.error.message }
              : null,
            totalVideoFrames: quality.totalVideoFrames,
            droppedVideoFrames: quality.droppedVideoFrames,
          };
        });
        receipt.observations.push({
          ...observation,
          elapsedSeconds: (performance.now() - began) / 1000,
        });
        await flush();
        if (observation.error) throw new Error("Encoded video playback failed");
        if (observation.ended) break;
        await new Promise((resolve) => setTimeout(resolve, 5000));
      }
      const last = receipt.observations.at(-1);
      assert.equal(last.ended, true, "Video did not finish full playback");
      assert.ok(last.currentTime >= 179.9);
    }
    const ffmpeg = RenderInternals.getExecutablePath({
      type: "ffmpeg",
      indent: false,
      logLevel: "warn",
      binariesDirectory: null,
    });
    const fullDecode = await runNative(
      ffmpeg,
      [
        "-hide_banner",
        "-nostdin",
        "-i",
        actualFile,
        "-c:v",
        "rawvideo",
        "-f",
        "null",
        "-",
      ],
      { maxBuffer: 4 * 1024 * 1024, timeout: 120000 },
    );
    await writeFile(
      path.join(outputDirectory, "native-full-decode.log"),
      fullDecode.stderr,
      { flag: "wx" },
    );
    assert.match(fullDecode.stderr, /frame=\s*5400\b/);
    receipt.nativeDecode = {
      method:
        "bundled FFmpeg CPU decoding; rawvideo/null full decode and native PNG samples",
      executable: ffmpeg,
      fullDecodeLogSha256: await hashFile(
        path.join(outputDirectory, "native-full-decode.log"),
      ),
    };
    // Every second plus close samples on either side of each chapter cut.
    const times = [
      ...new Set([
        ...Array.from({ length: 180 }, (_, index) => index + 0.5),
        11.9,
        12.1,
        34.9,
        35.1,
        69.9,
        70.1,
        109.9,
        110.1,
        139.9,
        140.1,
        164.9,
        165.1,
      ]),
    ].sort((a, b) => a - b);
    for (let index = 0; index < times.length; index++) {
      const seconds = times[index];
      const filename = `frame-${String(Math.round(seconds * 1000)).padStart(6, "0")}.png`;
      const nativePath = path.join(outputDirectory, filename);
      await runNative(
        ffmpeg,
        [
          "-hide_banner",
          "-loglevel",
          "error",
          "-nostdin",
          "-ss",
          String(seconds),
          "-i",
          actualFile,
          "-frames:v",
          "1",
          nativePath,
        ],
        { timeout: 30000 },
      );
      const pixels = (await readFile(nativePath)).toString("base64");
      const result = await page.evaluate(
        async (pixels, time, position, final) => {
          const canvas = new Image();
          canvas.src = `data:image/png;base64,${pixels}`;
          await canvas.decode();
          if (position % 12 === 0) {
            window.reviewSheet = document.createElement("canvas");
            window.reviewSheet.width = 1920;
            window.reviewSheet.height = 930;
          }
          const sheet = window.reviewSheet;
          const context = sheet.getContext("2d");
          const x = (position % 4) * 480;
          const y = Math.floor((position % 12) / 4) * 310;
          context.drawImage(canvas, x, y, 480, 270);
          context.fillStyle = "#101722";
          context.fillRect(x, y + 270, 480, 40);
          context.fillStyle = "#fff";
          context.font = "22px Arial";
          context.fillText(`${time.toFixed(1)} seconds`, x + 15, y + 297);
          return {
            sheet:
              position % 12 === 11 || final
                ? sheet.toDataURL("image/png").split(",")[1]
                : null,
          };
        },
        pixels,
        seconds,
        index,
        index === times.length - 1,
      );
      receipt.decodedFrames.push({
        seconds,
        file: filename,
        sha256: await hashFile(path.join(outputDirectory, filename)),
      });
      if (result.sheet) {
        const sheetName = `contact-${String(Math.floor(index / 12) + 1).padStart(2, "0")}.png`;
        await writeFile(
          path.join(outputDirectory, sheetName),
          Buffer.from(result.sheet, "base64"),
          { flag: "wx" },
        );
        receipt.contactSheets.push({
          file: sheetName,
          sha256: await hashFile(path.join(outputDirectory, sheetName)),
        });
        await flush();
      }
    }
    receipt.status = "passed";
    receipt.elapsedSeconds = (performance.now() - began) / 1000;
    await flush();
  },
  finalize: async (error, cleanupErrors) => {
    if (error || cleanupErrors.length) receipt.status = "failed";
    if (error) receipt.error = String(error);
    receipt.cleanupErrors = cleanupErrors;
    receipt.resourcesClosed = cleanupErrors.length === 0;
    await flush();
  },
});
