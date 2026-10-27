import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  slots,
  validateManifest,
  verifyAssets,
  containedFile,
  hashFile,
} from "./manifest.mjs";

const valid = () => ({
  schema: "marketlab-demo-v1",
  sourceFingerprint: "a".repeat(64),
  capturedAfterTimedAcceptance: true,
  reviewed: true,
  shots: slots.map(([id, from, duration]) => ({
    id,
    from,
    duration,
    title: id,
    file: `${id}.mp4`,
    sha256: "a".repeat(64),
    trimBefore: 0,
    sourceState: "fresh",
    disclosure: "",
    evidence: [{ path: "gate.json", sha256: "a".repeat(64) }],
    captions: [
      {
        text: "Verified local footage",
        startMs: 0,
        endMs: 3000,
        timestampMs: null,
        confidence: null,
      },
    ],
  })),
});
test("requires actual reviewed footage, evidence and fixed storyboard timing", () => {
  validateManifest(valid());
  for (const mutate of [
    (m) => (m.reviewed = false),
    (m) => m.shots.pop(),
    (m) => m.shots[0].duration++,
    (m) => (m.shots[0].evidence = []),
    (m) => (m.shots[0].file = "https://example.com/ui.mp4"),
    (m) => (m.shots[0].crop = { x: 1500, y: 0, width: 600, height: 300 }),
    (m) => (m.shots[0].captions[0].endMs = 999999),
  ]) {
    const value = valid();
    mutate(value);
    assert.throws(() => validateManifest(value));
  }
});
test("rejects path escape and changed evidence or footage", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "marketlab-demo-"));
  try {
    await mkdir(path.join(root, "media"));
    await mkdir(path.join(root, "evidence"));
    await writeFile(path.join(root, "evidence", "gate.json"), "{}");
    const value = valid();
    for (const shot of value.shots) {
      await writeFile(path.join(root, "media", shot.file), "actual-file");
      shot.sha256 = await hashFile(path.join(root, "media", shot.file));
      shot.evidence[0].sha256 = await hashFile(
        path.join(root, "evidence", "gate.json"),
      );
    }
    assert.equal(
      (
        await verifyAssets(
          value,
          path.join(root, "media"),
          path.join(root, "evidence"),
        )
      ).length,
      5,
    );
    await assert.rejects(() =>
      containedFile(path.join(root, "media"), "../evidence/gate.json"),
    );
    await writeFile(
      path.join(root, "evidence", "gate.json"),
      '{"changed":true}',
    );
    await assert.rejects(
      () =>
        verifyAssets(
          value,
          path.join(root, "media"),
          path.join(root, "evidence"),
        ),
      /Evidence hash mismatch/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
