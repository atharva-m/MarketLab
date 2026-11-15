// Records one real MarketLab workflow for the README demo.
// The page is captured with Chrome's screencast at 2x density while every
// pointer position, click, typing burst, scroll and worker command is logged
// with wall-clock timestamps. The cursor and click zooms are drawn later from
// this log, so each on-screen interaction corresponds to an actual input.
//
// Usage: node scripts/capture-workflow.mjs <connection.json> <fresh output dir> [--hero|--workspace]
// --hero ends the recording after the memo, which is all the README loop uses.
// --workspace records the same story on the Binance spot workspace (/v2).
import { chromium } from "../../frontend/node_modules/playwright/index.mjs";
import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const [connectionFile, outputDir, mode] = process.argv.slice(2);
if (
  !connectionFile ||
  !outputDir ||
  (mode && !["--hero", "--workspace"].includes(mode))
)
  throw new Error(
    "Usage: capture-workflow.mjs <connection.json> <output dir> [--hero|--workspace]",
  );
const heroOnly = mode === "--hero";
const workspace = mode === "--workspace";
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
  const click = async (
    locator,
    { dx = 0.5, dy = 0.5, zoom, shift = false } = {},
  ) => {
    const { x, y } = await target(locator, dx, dy);
    await glide(x, y);
    await sleep(140);
    if (shift) await page.keyboard.down("Shift");
    mark("down", { x, y, ...(zoom ? { zoom } : {}) });
    await page.mouse.down();
    await sleep(80);
    await page.mouse.up();
    mark("up", { x, y });
    if (shift) await page.keyboard.up("Shift");
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

  const day = (n) =>
    page.getByRole("button", { name: new RegExp(`^BTC/USDT, ${n} Jan:`) });
  const pin = (date) =>
    page.getByRole("checkbox", {
      name: new RegExp(`^Pin binance:spot:BTCUSDT ${date} `),
    });
  if (workspace) {
    await page.goto(`${ui}/#/v2/catalog`);
    await pin("2025-01-01").waitFor();
  } else {
    await page.goto(`${ui}/#/catalog`);
    await day(29).waitFor();
  }
  await sleep(600);

  // The same story on the Binance spot workspace: pin versions from the
  // catalog, submit a run, execute it, read results, chart and memo.
  const workspaceFlow = async () => {
    const field = (name) => page.getByLabel(name, { exact: true });
    const fill = async (name, text) => {
      await click(field(name), { dx: 0.3 });
      await type(text, 30);
      await sleep(250);
    };

    // 1. Narrow the catalog to the last January days and pin three versions.
    mark("chapter", { id: "catalog" });
    await click(field("From"), { dx: 0.06 });
    await type("01292025", 70);
    await sleep(350);
    await click(page.getByRole("button", { name: "Apply", exact: true }));
    await pin("2025-01-01").waitFor({ state: "detached" });
    await pin("2025-01-29").waitFor();
    await sleep(600);
    for (const date of ["2025-01-29", "2025-01-30", "2025-01-31"]) {
      await click(pin(date));
      await sleep(260);
    }
    await sleep(900);
    await click(page.getByRole("link", { name: "Run research", exact: true }));

    // 2. Describe and submit a deterministic research run.
    mark("chapter", { id: "research" });
    await field("History start").waitFor();
    await sleep(700);
    await fill("History start", "2025-01-29T00:00:00Z");
    await fill("Evaluation start", "2025-01-29T01:00:00Z");
    await fill("Evaluation end", "2025-02-01T00:00:00Z");
    const pinned = await target(page.locator(".table-wrap.pins"), 0.5, 0.6);
    await glide(pinned.x, pinned.y, 800);
    await sleep(900);
    await click(
      page.getByRole("checkbox", {
        name: "Confirm these versions and time range",
      }),
    );
    await sleep(350);
    await click(
      page.getByRole("button", { name: "Run research", exact: true }),
    );
    await page.waitForURL(/#\/v2\/runs\/[a-f0-9-]{36}$/, { timeout: 600000 });
    const runId = page.url().split("/").pop();
    log.run_id = runId;
    mark("submitted", { run: runId });
    await page.locator(".worker code").waitFor({ timeout: 60000 });
    await sleep(1600);

    // 3. A bounded research worker executes the queued run.
    mark("chapter", { id: "execute" });
    const command = await target(page.locator(".worker code"), 0.4, 0.5);
    await glide(command.x, command.y, 900);
    await worker([
      "marketlab.research_cli",
      "v2",
      "worker",
      "--max-runs",
      "1",
      "--run",
      runId,
    ]);
    const summary = page.getByRole("heading", { name: "Summary", exact: true });
    await summary.waitFor({ timeout: 120000 });
    mark("results-visible");
    await sleep(1500);

    // 4. Read the exact figures, then load a price window.
    mark("chapter", { id: "results" });
    const metrics = page.locator(".kv .table-wrap").first();
    await metrics.waitFor();
    await scrollTo(metrics, 110);
    const figures = await target(metrics, 0.45, 0.25);
    await glide(figures.x, figures.y, 800);
    await glide(figures.x + 40, figures.y + 190, 2200);
    await sleep(700);
    mark("chapter", { id: "chart" });
    await scrollTo(
      page.getByRole("heading", { name: "Chart", exact: true }),
      90,
    );
    await sleep(500);
    await fill("Start", "2025-01-29T01:00:00Z");
    await fill("End", "2025-02-01T00:00:00Z");
    await click(page.getByRole("button", { name: "Load chart", exact: true }));
    const chartSvg = page.locator("svg[aria-label^='Close price']");
    await chartSvg.waitFor({ timeout: 120000 });
    mark("chart-visible");
    await sleep(900);
    const chart = await target(chartSvg, 0.2, 0.4);
    await glide(chart.x, chart.y, 600);
    await glide(chart.x + chart.box.width * 0.55, chart.y + 30, 2200);
    await sleep(700);

    // 5. Queue the memo; the inference worker writes it.
    mark("chapter", { id: "memo" });
    const memoPanel = page.locator("section.memo");
    await scrollTo(memoPanel, 90);
    await sleep(900);
    const queue = memoPanel.getByRole("button", { name: "Queue memo" });
    if (await queue.isVisible()) {
      await click(queue);
      await sleep(1400);
    }
    await worker([
      "marketlab.memo_cli",
      "v2",
      "worker",
      "--max-jobs",
      "1",
      "--run",
      runId,
    ]);
    const paragraphs = memoPanel.locator(".v2-memo-text p");
    await paragraphs.nth(2).waitFor({ timeout: 300000 });
    mark("memo-visible");
    await sleep(1200);
    const memo = await target(memoPanel.locator(".v2-memo-text"), 0.1, 0.1);
    await glide(memo.x, memo.y, 800);
    await glide(
      memo.x + memo.box.width * 0.6,
      memo.y + memo.box.height * 0.75,
      2600,
    );
    await sleep(900);

    // 6. Ask the copilot about the same pinned versions. The end of the
    // window is deliberately omitted; the pinned model asks for it.
    mark("chapter", { id: "copilot" });
    await scroll(-(await page.evaluate(() => window.scrollY)), 1100);
    await click(
      page
        .getByRole("navigation", { name: "Workspace navigation" })
        .getByRole("link", { name: "Copilot", exact: true }),
    );
    const request = page.getByRole("textbox", { name: /^Research request/ });
    await request.waitFor();
    await sleep(700);
    await click(request, { dx: 0.3, dy: 0.3 });
    await type(
      "descriptive OHLCV market profile for BTCUSDT; history_start " +
        "2025-01-29T00:00:00Z; start 2025-01-29T01:00:00Z; 5m; metrics profile.",
      24,
    );
    await sleep(500);
    await click(
      page.getByRole("checkbox", { name: /^Confirm these versions/ }),
    );
    await sleep(350);
    await click(page.getByRole("button", { name: "Ask copilot", exact: true }));
    await page.waitForURL(/#\/v2\/copilot\/[a-f0-9-]{36}$/, {
      timeout: 120000,
    });
    const requestId = page.url().split("/").pop();
    log.request_id = requestId;
    mark("copilot-requested", { request: requestId });
    await page.getByText("Revision", { exact: true }).waitFor();
    await sleep(1400);
    const copilotWorker = () =>
      worker([
        "marketlab.copilot_cli",
        "v2",
        "worker",
        "--max-jobs",
        "1",
        "--request",
        requestId,
      ]);
    await copilotWorker();
    const answer = page.getByLabel("Clarification answer", { exact: true });
    const opened = page.getByRole("link", { name: "Open run", exact: true });
    await Promise.race([
      answer.waitFor({ timeout: 60000 }),
      opened.waitFor({ timeout: 60000 }),
    ]);
    if (await answer.isVisible()) {
      mark("clarification-visible");
      await sleep(1000);
      const question = await target(
        page.locator("article.revision").last().locator("dd").first(),
        0.3,
        0.5,
      );
      await glide(question.x, question.y, 900);
      await sleep(1400);
      await click(answer, { dx: 0.2, dy: 0.4 });
      await type("exclusive end 2025-02-01T00:00:00Z", 45);
      await sleep(500);
      await click(
        page.getByRole("button", { name: "Send answer", exact: true }),
      );
      await answer.waitFor({ state: "detached", timeout: 60000 });
      await sleep(1200);
      await copilotWorker();
    }
    await opened.waitFor({ timeout: 60000 });
    mark("copilot-submitted");
    await sleep(1300);
    await click(opened);
    await page.waitForURL(/#\/v2\/runs\/[a-f0-9-]{36}$/, { timeout: 60000 });
    const copilotRun = page.url().split("/").pop();
    log.copilot_run_id = copilotRun;
    mark("copilot-run-visible", { run: copilotRun });
    await page.locator(".worker code").waitFor({ timeout: 60000 });
    await sleep(1400);
    await worker([
      "marketlab.research_cli",
      "v2",
      "worker",
      "--max-runs",
      "1",
      "--run",
      copilotRun,
    ]);
    await summary.waitFor({ timeout: 120000 });
    mark("copilot-results-visible");
    await sleep(1200);
    await scrollTo(metrics, 110);
    const copilotFigures = await target(metrics, 0.45, 0.25);
    await glide(copilotFigures.x, copilotFigures.y, 800);
    await glide(copilotFigures.x + 40, copilotFigures.y + 190, 2200);
    await sleep(1600);
  };

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

  if (workspace) {
    await workspaceFlow();
  } else {
    // 1. Pin explicit dataset versions: a day, then shift-click to extend.
    mark("chapter", { id: "catalog" });
    await click(day(29));
    await sleep(500);
    await click(day(31), { shift: true });
    await sleep(900);
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
    if (!heroOnly) {
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
    }
  }
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
