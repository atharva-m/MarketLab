import { createHash } from "node:crypto";
import { readFile, realpath, stat } from "node:fs/promises";
import path from "node:path";

export const slots = [
  ["catalog", 360, 690],
  ["manual", 1050, 1050],
  ["copilot", 2100, 1200],
  ["memo", 3300, 900],
  ["monitoring", 4200, 750],
];
export const hashFile = async (filename) =>
  createHash("sha256")
    .update(await readFile(filename))
    .digest("hex");
const hashPattern = /^[a-f0-9]{64}$/;
const safeText = (text, maximum) =>
  typeof text === "string" &&
  text.length > 0 &&
  text.length <= maximum &&
  !/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(text);

export async function containedFile(root, relative) {
  if (
    typeof relative !== "string" ||
    !relative ||
    path.isAbsolute(relative) ||
    relative.includes(":") ||
    relative.includes("\\")
  )
    throw new Error("Expected local relative path");
  const actualRoot = await realpath(root);
  const actual = await realpath(path.resolve(actualRoot, relative));
  const difference = path.relative(actualRoot, actual);
  if (difference.startsWith("..") || path.isAbsolute(difference))
    throw new Error("Path escapes local asset root");
  const entry = await stat(actual);
  if (!entry.isFile()) throw new Error("Expected regular file");
  return actual;
}

export function validateManifest(manifest) {
  if (
    manifest?.schema !== "marketlab-demo-v1" ||
    !hashPattern.test(manifest.sourceFingerprint) ||
    manifest.capturedAfterTimedAcceptance !== true ||
    manifest.reviewed !== true
  )
    throw new Error("Expected reviewed current-source evidence manifest");
  if (!Array.isArray(manifest.shots) || manifest.shots.length !== slots.length)
    throw new Error("Five shots required");
  for (let index = 0; index < slots.length; index++) {
    const shot = manifest.shots[index];
    const [id, from, duration] = slots[index];
    if (
      shot.id !== id ||
      shot.from !== from ||
      shot.duration !== duration ||
      !Number.isInteger(shot.trimBefore) ||
      shot.trimBefore < 0
    )
      throw new Error("Shot timing/order mismatch");
    if (
      !safeText(shot.title, 70) ||
      !["fresh", "retained"].includes(shot.sourceState) ||
      typeof shot.disclosure !== "string" ||
      shot.disclosure.length > 120 ||
      !hashPattern.test(shot.sha256)
    )
      throw new Error("Invalid shot fields");
    if (
      typeof shot.file !== "string" ||
      !/^[a-z0-9][a-z0-9/_-]*\.(mp4|webm)$/.test(shot.file) ||
      shot.file.includes("..")
    )
      throw new Error("Only local video paths are accepted");
    if (shot.crop !== undefined) {
      const { x, y, width, height } = shot.crop;
      if (
        ![x, y, width, height].every(Number.isInteger) ||
        x < 0 ||
        y < 0 ||
        width < 320 ||
        height < 180 ||
        x + width > 1920 ||
        y + height > 1080
      )
        throw new Error(
          "Crop must stay within the recorded 1920x1080 viewport",
        );
    }
    if (
      !Array.isArray(shot.evidence) ||
      !shot.evidence.length ||
      shot.evidence.some(
        (entry) =>
          typeof entry?.path !== "string" || !hashPattern.test(entry.sha256),
      )
    )
      throw new Error("Hashed evidence references required");
    if (!Array.isArray(shot.captions) || !shot.captions.length)
      throw new Error("Reviewed captions required");
    let previousEnd = 0;
    for (const caption of shot.captions) {
      if (
        !safeText(caption.text, 240) ||
        !Number.isInteger(caption.startMs) ||
        !Number.isInteger(caption.endMs) ||
        caption.startMs < previousEnd ||
        caption.endMs <= caption.startMs ||
        caption.endMs > (duration / 30) * 1000 ||
        caption.timestampMs !== null ||
        caption.confidence !== null
      )
        throw new Error("Invalid caption timing or text");
      previousEnd = caption.endMs;
    }
  }
  return manifest;
}

export async function verifyAssets(manifest, mediaRoot, evidenceRoot) {
  validateManifest(manifest);
  const files = [];
  for (const shot of manifest.shots) {
    const actual = await containedFile(mediaRoot, shot.file);
    if ((await hashFile(actual)) !== shot.sha256)
      throw new Error(`Clip hash mismatch: ${shot.id}`);
    for (const evidence of shot.evidence) {
      const file = await containedFile(evidenceRoot, evidence.path);
      if ((await hashFile(file)) !== evidence.sha256)
        throw new Error(`Evidence hash mismatch: ${shot.id}`);
    }
    files.push(actual);
  }
  return files;
}
