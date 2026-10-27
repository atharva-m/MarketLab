import { bundle } from "@remotion/bundler";
import {
  openBrowser,
  selectComposition,
  renderMedia,
  renderStill,
} from "@remotion/renderer";
import { readFile, writeFile, stat, readdir } from "node:fs/promises";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { hashFile, validateManifest, containedFile } from "./manifest.mjs";
import { inspectDedicatedGpu } from "./gpu.mjs";

const [propsFile, output, mode = "final"] = process.argv.slice(2);
if (
  !propsFile ||
  !output ||
  !["final", "setup-check", "media-check", "gpu-probe"].includes(mode)
)
  throw new Error(
    "Usage: npm run render:local -- props.json output.mp4 [final|setup-check|media-check|gpu-probe]",
  );
try {
  await stat(output);
  throw new Error("Output exists; use a new invocation path");
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}
const props =
  mode === "setup-check" ? {} : JSON.parse(await readFile(propsFile, "utf8"));
const productProps = mode === "final" || mode === "gpu-probe";
if (productProps) {
  validateManifest(props.manifest);
  for (const shot of props.manifest.shots) {
    const file = await containedFile("public", shot.file);
    if ((await hashFile(file)) !== shot.sha256)
      throw new Error(`Prepared asset changed: ${shot.id}`);
  }
}
if (mode === "media-check") {
  if (!/^media\/[a-z0-9-]+\.mp4$/.test(props.setupFile))
    throw new Error("Expected local setup clip");
  await containedFile("public", props.setupFile);
}
const started = performance.now();
const sourceFiles = [
  "package.json",
  "package-lock.json",
  "provenance.json",
  "remotion.config.ts",
  ...(await readdir("src")).map((name) => `src/${name}`),
  ...(await readdir("scripts")).map((name) => `scripts/${name}`),
].sort();
const sourceHashes = Object.fromEntries(
  await Promise.all(
    sourceFiles.map(async (file) => [file, await hashFile(file)]),
  ),
);
if (productProps) process.env.R9_VIDEO_GPU = "1";
const serveUrl = await bundle({
  entryPoint: path.resolve("src/index.ts"),
  rspack: true,
});
const browser = await openBrowser("chrome", {
  logLevel: "warn",
  ...(productProps ? { chromiumOptions: { gl: "angle" } } : {}),
});
try {
  const gpu = productProps ? await inspectDedicatedGpu(browser) : null;
  const encoderArguments = [];
  let renderStart = null;
  let latestProgress = null;
  let lastProgressAt = 0;
  const composition = await selectComposition({
    serveUrl,
    id: productProps
      ? "MarketLabR9"
      : mode === "media-check"
        ? "MediaSetupCheck"
        : "SetupPreview",
    inputProps: props,
    puppeteerInstance: browser,
  });
  await renderMedia({
    composition,
    serveUrl,
    inputProps: props,
    codec: "h264",
    outputLocation: path.resolve(output),
    puppeteerInstance: browser,
    concurrency: 2,
    overwrite: false,
    pixelFormat: "yuv420p",
    logLevel: "info",
    ...(productProps
      ? { hardwareAcceleration: "required", videoBitrate: "8M", crf: null }
      : {}),
    ...(mode === "gpu-probe" ? { frameRange: [3600, 3629] } : {}),
    onStart: (value) => {
      renderStart = value;
    },
    ffmpegOverride: ({ type, args }) => {
      const encoderIndex = args.indexOf("h264_nvenc");
      const actual =
        encoderIndex >= 0
          ? [
              ...args.slice(0, encoderIndex + 1),
              "-gpu",
              "0",
              ...args.slice(encoderIndex + 1),
            ]
          : args;
      encoderArguments.push({ type, args: actual });
      return actual;
    },
    onProgress: (value) => {
      latestProgress = {
        renderedFrames: value.renderedFrames,
        encodedFrames: value.encodedFrames,
        stitchStage: value.stitchStage,
      };
      if (performance.now() - lastProgressAt > 10000) {
        lastProgressAt = performance.now();
        writeFileSync(
          `${output}.progress.json`,
          JSON.stringify({
            status: "running",
            elapsedSeconds: (performance.now() - started) / 1000,
            ...latestProgress,
          }),
        );
        console.log(JSON.stringify(latestProgress));
      }
    },
  });
  if (
    productProps &&
    !encoderArguments.some((entry) => entry.args.includes("h264_nvenc"))
  )
    throw new Error(
      "Required NVENC encoder was not observed in actual encoding arguments",
    );
  await renderStill({
    composition,
    serveUrl,
    inputProps: props,
    frame: mode === "final" ? 450 : mode === "gpu-probe" ? 3600 : 40,
    output: `${output}.sample.png`,
    puppeteerInstance: browser,
    overwrite: false,
  });
  if (productProps)
    await renderStill({
      composition,
      serveUrl,
      inputProps: props,
      frame: 4500,
      output: `${output}.provenance.png`,
      puppeteerInstance: browser,
      overwrite: false,
    });
  for (const [file, hash] of Object.entries(sourceHashes))
    if ((await hashFile(file)) !== hash)
      throw new Error(`Video source changed during render: ${file}`);
  await writeFile(
    `${output}.receipt.json`,
    JSON.stringify(
      {
        schema: "marketlab-demo-render-v1",
        status: "passed",
        scope:
          mode === "final"
            ? "final video; visual review pending"
            : mode === "gpu-probe"
              ? "30-frame GPU compatibility probe from real footage; no final demo credit"
              : "setup-only; no product footage; no final acceptance credit",
        mode,
        remotion: "4.0.539",
        durationInFrames:
          mode === "gpu-probe" ? 30 : composition.durationInFrames,
        compositionDurationInFrames: composition.durationInFrames,
        fps: composition.fps,
        width: composition.width,
        height: composition.height,
        elapsedSeconds: (performance.now() - started) / 1000,
        outputSha256: await hashFile(output),
        propsSha256: productProps ? await hashFile(propsFile) : null,
        sourceFingerprint: props.manifest?.sourceFingerprint ?? null,
        demoSourceHashes: sourceHashes,
        gpu,
        encoding: productProps
          ? {
              hardwareAcceleration: "required",
              encoder: "h264_nvenc",
              videoBitrate: "8M",
              crf: null,
              encoderArguments,
            }
          : { hardwareAcceleration: "disable" },
        renderStart,
        latestProgress,
        controls:
          "Node loopback socket guard and Chromium loopback proxy/DNS flags; no system network changes",
        limitations:
          "Process controls are not a host-wide packet capture or guarantee about unrelated processes.",
      },
      null,
      2,
    ),
    { flag: "wx" },
  );
} finally {
  await browser.close({ silent: true });
}
