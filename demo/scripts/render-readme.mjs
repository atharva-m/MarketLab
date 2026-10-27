// Renders a README composition master from prepared props.
// Usage: npm run render:readme -- <props.json> <master.mp4> <ReadmeHero|ReadmeHighlight>
import { bundle } from "@remotion/bundler";
import {
  openBrowser,
  renderMedia,
  selectComposition,
} from "@remotion/renderer";
import { readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { hashFile } from "./manifest.mjs";

const [propsFile, output, id] = process.argv.slice(2);
if (!propsFile || !output || !["ReadmeHero", "ReadmeHighlight"].includes(id))
  throw new Error(
    "Usage: npm run render:readme -- props.json master.mp4 ReadmeHero|ReadmeHighlight",
  );
try {
  await stat(output);
  throw new Error("Output exists; use a new path");
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}
const inputProps = JSON.parse(await readFile(propsFile, "utf8"));
const media = path.resolve("public", inputProps.timeline.video);
await stat(media);
const started = performance.now();
const serveUrl = await bundle({
  entryPoint: path.resolve("src/index.ts"),
  rspack: true,
});
const browser = await openBrowser("chrome", { logLevel: "warn" });
try {
  const composition = await selectComposition({
    serveUrl,
    id,
    inputProps,
    puppeteerInstance: browser,
  });
  let last = 0;
  await renderMedia({
    composition,
    serveUrl,
    inputProps,
    codec: "h264",
    crf: 12,
    x264Preset: "medium",
    pixelFormat: "yuv420p",
    outputLocation: path.resolve(output),
    puppeteerInstance: browser,
    overwrite: false,
    logLevel: "warn",
    onProgress: ({ renderedFrames, encodedFrames }) => {
      if (performance.now() - last > 10000) {
        last = performance.now();
        console.log(JSON.stringify({ renderedFrames, encodedFrames }));
      }
    },
  });
  await writeFile(
    `${output}.receipt.json`,
    JSON.stringify(
      {
        schema: "marketlab-readme-render-v1",
        composition: id,
        frames: composition.durationInFrames,
        fps: composition.fps,
        width: composition.width,
        height: composition.height,
        seconds: (performance.now() - started) / 1000,
        outputSha256: await hashFile(output),
        propsSha256: await hashFile(propsFile),
        screenSha256: await hashFile(media),
      },
      null,
      2,
    ),
    { flag: "wx" },
  );
  console.log(`Rendered ${output}`);
} finally {
  await browser.close({ silent: true });
}
