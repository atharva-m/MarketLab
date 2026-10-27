// Records one real MarketLab workflow for the README demo.
// The page is captured with Chrome's screencast at 2x density while every
// pointer position, click, typing burst, scroll and worker command is logged
// with wall-clock timestamps. The cursor and click zooms are drawn later from
// this log, so each on-screen interaction corresponds to an actual input.
//
// Usage: node scripts/capture-workflow.mjs <connection.json> <fresh output dir>
import { chromium } from "../../frontend/node_modules/playwright/index.mjs";
import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const [connectionFile, outputDir] = process.argv.slice(2);
if (!connectionFile || !outputDir)
  throw new Error("Usage: capture-workflow.mjs <connection.json> <output dir>");
const project = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const connection = JSON.parse(
  (await readFile(connectionFile, "utf8")).replace(/^﻿/, ""),
);
const ui = "http://127.0.0.1:5173";
const viewport = { width: 1440, height: 810 };
const dpr = 2;
const out = path.resolve(outputDir);
await mkdir(out, { recursive: false });
await mkdir(path.join(out, "frames"));

const log = {
  schema: "marketlab-capture-v1",
  status: "running",
  viewport,
  dpr,
  frames: [],
  pointer: [],
  events: [],
  errors: [],
};
const now = () => Date.now();
const mark = (type, data = {}) => log.events.push({ t: now(), type, ...data });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const save = () =>
  writeFile(path.join(out, "capture.json"), JSON.stringify(log, null, 1));

const workerEnv = {
  ...process.env,
  MARKETLAB_DATABASE_URL: connection.database_url,
  MARKETLAB_REDIS_URL: connection.redis_url,
  MARKETLAB_STORAGE_PATH: connection.storage_path,
  MARKETLAB_OLLAMA_URL: connection.ollama_url,
  MARKETLAB_METRICS_PORT: "0",
};
delete workerEnv.MARKETLAB_DATABASE_PASSWORD;

// Runs one bounded CLI worker exactly as an operator would and logs it.
const worker = (args) =>
  new Promise((resolve, reject) => {
    const display = `python -m ${args.join(" ")}`;
    mark("command-start", { display });
    const child = spawn(
      path.join(project, ".venv", "Scripts", "python.exe"),
      ["-m", ...args],
      { cwd: project, env: workerEnv, windowsHide: true },
    );
    let stderr = "";
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("error", reject);
    child.on("exit", (code) => {
      mark("command-end", { display, code });
      if (code === 0) resolve();
      else
        reject(new Error(`${display} exited ${code}: ${stderr.slice(-800)}`));
    });
  });

// Without the forced factor, headless screencast frames arrive at 1x size.
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: [`--force-device-scale-factor=${dpr}`],
});
let page;
let cdp;
let writes = [];
try {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: dpr,
  });
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (
      url.origin === ui ||
      ["about:", "data:", "blob:"].includes(url.protocol)
    )
      return route.continue();
    return route.abort("blockedbyclient");
  });
  page = await context.newPage();
  page.on("pageerror", (error) => log.errors.push(String(error)));
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) mark("nav", { url: frame.url() });
  });

  let pointer = { x: 760, y: 470 };
  await page.mouse.move(pointer.x, pointer.y);
  const glide = async (x, y, ms = 700) => {
    const from = { ...pointer };
    const distance = Math.hypot(x - from.x, y - from.y);
    const duration = Math.max(260, Math.min(ms, 260 + distance * 0.9));
    // A slight perpendicular bow keeps the path from looking robotic.
    const bow = Math.min(60, distance * 0.08);
    const nx = distance ? -(y - from.y) / distance : 0;
    const ny = distance ? (x - from.x) / distance : 0;
    const start = performance.now();
    for (;;) {
      const p = Math.min(1, (performance.now() - start) / duration);
      const e = p < 0.5 ? 4 * p ** 3 : 1 - (-2 * p + 2) ** 3 / 2;
      const arc = Math.sin(Math.PI * e) * bow;
      pointer = {
        x: from.x + (x - from.x) * e + nx * arc,
        y: from.y + (y - from.y) * e + ny * arc,
      };
      await page.mouse.move(pointer.x, pointer.y);
      log.pointer.push({ t: now(), x: pointer.x, y: pointer.y });
      if (p >= 1) break;
      await sleep(12);
    }
  };
  const target = async (locator, dx = 0.5, dy = 0.5) => {
    await locator.scrollIntoViewIfNeeded();
    const box = await locator.boundingBox();
    if (!box) throw new Error("Target is not visible");
    return { x: box.x + box.width * dx, y: box.y + box.height * dy, box };
  };
  const click = async (locator, { dx = 0.5, dy = 0.5, zoom } = {}) => {
    const { x, y } = await target(locator, dx, dy);
    await glide(x, y);
    await sleep(140);
    mark("down", { x, y, ...(zoom ? { zoom } : {}) });
    await page.mouse.down();
    await sleep(80);
    await page.mouse.up();
    mark("up", { x, y });
  };
  const type = async (text, delay = 38) => {
    mark("type-start", { text });
    await page.keyboard.type(text, { delay });
    mark("type-end");
  };
  const replace = async (locator, text) => {
    await click(locator, { dx: 0.85 });
    await page.keyboard.press("Control+A");
    await type(text);
  };
  const scroll = async (dy, ms = 700) => {
    mark("scroll-start", { dy });
    const steps = Math.max(1, Math.round(ms / 16));
    let done = 0;
    for (let i = 1; i <= steps; i++) {
      const p = i / steps;
      const e = p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2;
      const next = Math.round(dy * e);
      await page.mouse.wheel(0, next - done);
      done = next;
      await sleep(16);
    }
    await sleep(250);
    mark("scroll-end");
  };
  const scrollTo = async (locator, top = 110) => {
    const box = await locator.boundingBox();
    if (box) await scroll(box.y - top, 900);
  };

  await page.goto(`${ui}/#/catalog`);
  await page.getByRole("checkbox", { name: /BTCUSDT 2025-01-29/ }).waitFor();
  await sleep(600);

  cdp = await context.newCDPSession(page);
  let index = 0;
  cdp.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
    const file = `frames/${String(index++).padStart(6, "0")}.jpg`;
    log.frames.push({ file, t: metadata.timestamp * 1000 });
    writes.push(writeFile(path.join(out, file), Buffer.from(data, "base64")));
    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", {
    format: "jpeg",
    quality: 92,
    maxWidth: viewport.width * dpr,
    maxHeight: viewport.height * dpr,
    everyNthFrame: 1,
  });
  mark("record-start");
  await sleep(1200);

  // 1. Pin explicit dataset versions in the catalog.
  mark("chapter", { id: "catalog" });
  for (const day of ["31", "30", "29"]) {
    await click(
      page.getByRole("checkbox", {
        name: new RegExp(`BTCUSDT 2025-01-${day}`),
      }),
    );
    await sleep(380);
  }
  await sleep(500);
  await click(page.getByRole("link", { name: "Research with 3 selected" }));

  // 2. Describe and submit a deterministic research run.
  mark("chapter", { id: "research" });
  await page.getByTestId("evaluation-start").waitFor();
  await sleep(700);
  await replace(page.getByTestId("evaluation-start"), "2025-01-29T01:00:00Z");
  await sleep(300);
  await replace(page.getByTestId("history-start"), "2025-01-29T00:00:00Z");
  await sleep(400);
  const versions = await target(
    page.getByTestId("dataset-version-ids"),
    0.3,
    0.45,
  );
  await glide(versions.x, versions.y, 800);
  await sleep(900);
  await scrollTo(page.getByTestId("submit-research"), 520);
  await click(page.getByTestId("submit-research"));
  await page.waitForURL(/#\/runs\/[a-f0-9-]{36}$/, { timeout: 600000 });
  const runId = page.url().split("/").pop();
  log.run_id = runId;
  mark("submitted", { run: runId });
  await page.getByTestId("run-id").waitFor();
  await sleep(1600);

  // 3. A bounded research worker executes the queued run.
  mark("chapter", { id: "execute" });
  await glide(1010, 300, 900);
  await worker([
    "marketlab.research_cli",
    "worker",
    "--max-runs",
    "1",
    "--run",
    runId,
  ]);
  await page.getByTestId("numerical-summary").waitFor({ timeout: 120000 });
  mark("results-visible");
  await sleep(1500);
  const summary = await target(
    page.getByTestId("numerical-summary"),
    0.5,
    0.15,
  );
  await glide(summary.x, summary.y, 800);
  await sleep(600);

  // 4. Load an exact price/volume window.
  mark("chapter", { id: "chart" });
  const chartHeading = page.getByRole("heading", {
    name: "Price and base volume",
  });
  await scrollTo(chartHeading, 90);
  await sleep(500);
  await click(page.getByRole("button", { name: "Load chart window" }));
  await page
    .locator("svg[aria-label*='price candles']")
    .waitFor({ timeout: 120000 });
  mark("chart-visible");
  await sleep(900);
  const chart = await target(
    page.locator("svg[aria-label*='price candles']"),
    0.2,
    0.4,
  );
  await glide(chart.x, chart.y, 600);
  await glide(chart.x + chart.box.width * 0.55, chart.y + 30, 2200);
  await sleep(700);

  // 5. The shared inference worker writes the grounded memo.
  mark("chapter", { id: "memo" });
  await scrollTo(page.getByTestId("memo-panel"), 90);
  await sleep(1200);
  await worker(["marketlab.inference_cli", "worker", "--max-jobs", "1"]);
  await page
    .getByTestId("memo-panel")
    .locator(".memo-content p")
    .nth(2)
    .waitFor({ timeout: 300000 });
  mark("memo-visible");
  await sleep(1200);
  const memo = await target(
    page.getByTestId("memo-panel").locator(".memo-content"),
    0.1,
    0.1,
  );
  await glide(memo.x, memo.y, 800);
  await glide(
    memo.x + memo.box.width * 0.6,
    memo.y + memo.box.height * 0.75,
    2600,
  );
  await sleep(900);

  // 6. Ask the copilot; it must clarify the missing asset before submitting.
  mark("chapter", { id: "copilot" });
  await click(page.getByRole("link", { name: "Copilot" }));
  const request = page.getByRole("textbox", { name: /^Research request/ });
  await request.waitFor();
  await sleep(700);
  await click(request, { dx: 0.3, dy: 0.3 });
  // The asset is deliberately omitted; the pinned model asks for it.
  await type(
    "Produce a descriptive OHLCV market_profile on 5m bars; metrics profile; " +
      "inclusive start 2025-01-29T01:00:00Z, exclusive end 2025-02-01T00:00:00Z, " +
      "history from 2025-01-29T00:00:00Z.",
    24,
  );
  await sleep(600);
  await click(page.getByRole("button", { name: "Submit copilot request" }));
  await page.waitForURL(/#\/copilot\/[a-f0-9-]{36}$/, { timeout: 120000 });
  const requestId = page.url().split("/").pop();
  log.request_id = requestId;
  await page.getByRole("heading", { name: "Copilot request" }).waitFor();
  await sleep(1400);
  await worker([
    "marketlab.copilot_cli",
    "worker",
    "--max-jobs",
    "1",
    "--request",
    requestId,
  ]);
  const answer = page.getByLabel("Clarification answer", { exact: true });
  const opened = page.getByRole("link", { name: "Open research run" });
  await Promise.race([
    answer.waitFor({ timeout: 60000 }),
    opened.waitFor({ timeout: 60000 }),
  ]);
  if (await answer.isVisible()) {
    mark("clarification-visible");
    await sleep(1200);
    const questions = await target(
      page.locator("article.revision").last(),
      0.3,
      0.5,
    );
    await glide(questions.x, questions.y, 900);
    await sleep(1200);
    await click(answer, { dx: 0.2, dy: 0.4 });
    await type("BTCUSDT", 70);
    await sleep(500);
    await click(page.getByRole("button", { name: "Submit clarification" }));
    await sleep(1500);
    await worker([
      "marketlab.copilot_cli",
      "worker",
      "--max-jobs",
      "1",
      "--request",
      requestId,
    ]);
  }
  await opened.waitFor({ timeout: 60000 });
  mark("copilot-submitted");
  await scrollTo(page.locator("p.notice").first(), 160);
  await sleep(1200);
  await click(opened);
  await page.getByTestId("run-id").waitFor();
  const copilotRun = page.url().split("/").pop();
  log.copilot_run_id = copilotRun;
  mark("copilot-run-visible", { run: copilotRun });
  await sleep(1500);
  await worker([
    "marketlab.research_cli",
    "worker",
    "--max-runs",
    "1",
    "--run",
    copilotRun,
  ]);
  await page.getByTestId("numerical-summary").waitFor({ timeout: 120000 });
  mark("copilot-results-visible");
  await sleep(1200);
  const copilotSummary = await target(
    page.getByTestId("numerical-summary"),
    0.5,
    0.15,
  );
  await glide(copilotSummary.x, copilotSummary.y, 900);
  await sleep(2200);
  mark("record-end");
  log.status = "passed";
} catch (error) {
  log.status = "failed";
  log.error = String(error?.stack ?? error);
} finally {
  try {
    if (cdp) await cdp.send("Page.stopScreencast");
  } catch (error) {
    log.errors.push(`stop: ${error}`);
  }
  await Promise.all(writes);
  await browser.close();
  await save();
}
console.log(
  JSON.stringify({
    status: log.status,
    frames: log.frames.length,
    error: log.error,
  }),
);
if (log.status !== "passed") process.exitCode = 1;
