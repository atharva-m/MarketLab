import { mkdir, readFile, writeFile, copyFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { constants } from "node:fs";
import { getVideoMetadata } from "@remotion/renderer";
import { validateManifest, verifyAssets, hashFile } from "./manifest.mjs";

const [input, mediaRoot, evidenceRoot, outputDirectory] = process.argv.slice(2);
if (!input || !mediaRoot || !evidenceRoot || !outputDirectory)
  throw new Error(
    "Usage: npm run prepare:media -- manifest.json media-root evidence-root fresh-output-directory",
  );
const root = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const manifest = validateManifest(JSON.parse(await readFile(input, "utf8")));
const assets = await verifyAssets(manifest, mediaRoot, evidenceRoot);
const sourceMetadata = [];
// Metadata is read locally; clip truncation may not be hidden by frozen final frames.
for (let index = 0; index < assets.length; index++) {
  const metadata = await getVideoMetadata(assets[index]);
  const shot = manifest.shots[index];
  if (shot.crop && (metadata.width !== 1920 || metadata.height !== 1080))
    throw new Error(`Crop requires original 1920x1080 recording: ${shot.id}`);
  if (metadata.durationInSeconds * 30 + 0.5 < shot.trimBefore + shot.duration)
    throw new Error(`Clip too short: ${shot.id}`);
  sourceMetadata.push({
    id: shot.id,
    width: metadata.width,
    height: metadata.height,
    durationInSeconds: metadata.durationInSeconds,
    crop: shot.crop ?? null,
  });
}
await mkdir(outputDirectory, { recursive: false });
await mkdir(path.join(root, "public", "media"), { recursive: true });
const prepared = structuredClone(manifest);
for (let index = 0; index < assets.length; index++) {
  const shot = prepared.shots[index];
  const filename = `${shot.id}-${shot.sha256}${path.extname(shot.file)}`;
  const destination = path.join(root, "public", "media", filename);
  try {
    await copyFile(assets[index], destination, constants.COPYFILE_EXCL);
  } catch (error) {
    if (
      error.code !== "EEXIST" ||
      (await hashFile(destination)) !== shot.sha256
    )
      throw error;
  }
  shot.file = `media/${filename}`;
}
await writeFile(
  path.join(outputDirectory, "props.json"),
  JSON.stringify({ manifest: prepared }, null, 2),
  { flag: "wx" },
);
await writeFile(
  path.join(outputDirectory, "asset-receipt.json"),
  JSON.stringify(
    {
      schema: "marketlab-demo-assets-v1",
      input_sha256: await hashFile(input),
      sourceFingerprint: manifest.sourceFingerprint,
      sourceMetadata,
      shots: prepared.shots.map((shot) => ({
        id: shot.id,
        file: shot.file,
        sha256: shot.sha256,
        evidence: shot.evidence,
        crop: shot.crop ?? null,
      })),
    },
    null,
    2,
  ),
  { flag: "wx" },
);
const srtTime = (milliseconds) =>
  new Date(milliseconds).toISOString().slice(11, 23).replace(".", ",");
const captions = prepared.shots.flatMap((shot) =>
  shot.captions.map((caption) => ({
    text: caption.text,
    start: (shot.from / 30) * 1000 + caption.startMs,
    end: (shot.from / 30) * 1000 + caption.endMs,
  })),
);
await writeFile(
  path.join(outputDirectory, "captions.srt"),
  captions
    .map(
      (caption, index) =>
        `${index + 1}\n${srtTime(caption.start)} --> ${srtTime(caption.end)}\n${caption.text}\n`,
    )
    .join("\n"),
  { flag: "wx" },
);
await writeFile(
  path.join(outputDirectory, "transcript.txt"),
  "MarketLab. From explicit data to inspectable research.\n\n" +
    captions.map((caption) => caption.text).join("\n") +
    "\n\nInspect the evidence. Reproduce the research.\n",
  { flag: "wx" },
);
console.log(
  `Prepared verified local footage and props in ${path.resolve(outputDirectory)}`,
);
