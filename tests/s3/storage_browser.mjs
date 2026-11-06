// Deferred real-browser cases using the existing UI and ordinary bounded CLI workers.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const require = createRequire(path.join(root, "frontend/package.json"));
const { chromium, firefox, webkit } = require("playwright");
const { expect } = require("@playwright/test");
const plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const folder = path.dirname(process.argv[2]);
assert.equal(process.env.MARKETLAB_PHASE6_OWNED_S3, "confirmed-disposable-prefix");
assert.equal(plan.schema, "phase6-browser-v1");
assert.ok(["chromium", "firefox", "webkit"].includes(plan.engine));
const receipt = { schema: plan.schema, engine: plan.engine, mode: plan.mode, state: "running" };
const errors = [];
const browserEnv = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
  !key.startsWith("AWS_") && !key.startsWith("MARKETLAB_STORAGE_S3_") &&
  !key.startsWith("MARKETLAB_PHASE6_RESTORE_S3_") && !key.startsWith("MARKETLAB_PHASE6_EXPIRED_S3_") &&
  !["S3_BUCKET_NAME", "MARKETLAB_PHASE6_REDACTION_VALUES"].includes(key)));
const launchOptions = { headless: true, env: browserEnv };
if (plan.engine === "firefox") {
  const executable = "C:/Users/athar/AppData/Local/Temp/marketlab-phase6-playwright/firefox-1555/firefox/firefox.exe";
  assert.equal(fs.realpathSync(process.env.MARKETLAB_PHASE6_FIREFOX_EXECUTABLE), fs.realpathSync(executable));
  assert.equal(createHash("sha256").update(fs.readFileSync(executable)).digest("hex"), "c949e57fba9a65ab6c434a76e32d2c72eb43f8b99a7c48ee7e927a4fad4b2a36");
  launchOptions.executablePath = executable;
}
const browser = await ({ chromium, firefox, webkit })[plan.engine].launch(launchOptions);
const page = await browser.newPage();
page.setDefaultTimeout(120000);
page.on("pageerror", error => errors.push(error.message));
const save = () => fs.writeFileSync(path.join(folder, "receipt.json"), JSON.stringify(receipt, null, 2));
save();

function worker(kind, id) {
  assert.match(id, /^[0-9a-f-]{36}$/);
  const flags = {
    ingestion: ["marketlab.dataset_cli", "--max-jobs", "--submission"],
    research: ["marketlab.research_cli", "--max-runs", "--run"],
    copilot: ["marketlab.copilot_cli", "--max-jobs", "--request"],
    memo: ["marketlab.memo_cli", "--max-jobs", "--run"],
  }[kind];
  const result = spawnSync(
    process.env.MARKETLAB_PHASE6_PYTHON,
    ["-I", "-S", path.join(root, "artifacts/v2-phase6-s3-acceptance/guarded_python.py"),
      "--", "-m", flags[0], "v2", "worker", flags[1], "1", flags[2], id],
    { cwd: root, env: process.env, windowsHide: true, encoding: "utf8", timeout: 1860000, maxBuffer: 16 * 1024 ** 2 },
  );
  // Parent OwnedJob's bounded anonymous pipe is the only diagnostic route.
  if (!result.error) {
    process.stdout.write(result.stdout ?? "");
    process.stderr.write(result.stderr ?? "");
  }
  fs.writeFileSync(path.join(folder, `${kind}-worker.txt`), JSON.stringify({
    status: result.status, signal: result.signal, output_forwarded: !result.error,
    error_type: result.error?.name ?? null,
  }));
  assert.equal(result.status, 0);
}
async function get(url) {
  return await page.evaluate(async endpoint => {
    const response = await fetch(endpoint, { credentials: "same-origin", redirect: "error" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }, url);
}
async function click(endpoint, button) {
  const pending = page.waitForResponse(response =>
    new URL(response.url()).pathname === endpoint && response.request().method() === "POST",
    { timeout: 1860000 },
  );
  await button.click();
  const response = await pending;
  assert.ok(response.ok(), `HTTP ${response.status()}`);
  return await response.json();
}

try {
  if (plan.mode === "official") {
    const spec = plan.official;
    await page.goto(plan.ui_url + "/#/v2/ingestion/new");
    const group = page.getByRole("group", { name: "Choose 1–2 enabled Binance instruments" });
    for (const identity of spec.instrument_ids) {
      const match = /^binance:spot:(BTC|ETH|SOL)USDT$/.exec(identity);
      assert.ok(match);
      await expect(group.getByRole("checkbox", { name: new RegExp(`^${match[1]}/USDT`) })).toBeVisible();
    }
    for (const asset of ["BTC", "ETH", "SOL"]) {
      const field = group.getByRole("checkbox", { name: new RegExp(`^${asset}/USDT`) });
      if (await field.count()) await field.setChecked(spec.instrument_ids.includes(`binance:spot:${asset}USDT`));
    }
    await expect(group.getByRole("checkbox", { checked: true })).toHaveCount(spec.instrument_ids.length);
    await expect(page.getByText(`Selected instruments: ${spec.instrument_ids.join(", ")}`, { exact: true })).toBeVisible();
    await page.getByLabel("From UTC date (inclusive)", { exact: true }).fill(spec.from_date);
    await page.getByLabel("Before UTC date (exclusive)", { exact: true }).fill(spec.before_date);
    await page.getByRole("checkbox", { name: /I confirm these instruments and UTC daily boundaries/ }).check();
    const created = await click("/v2/ingestion/submissions", page.getByRole("button", { name: "Submit official ingestion" }));
    const id = created.id ?? created.submission_id;
    worker("ingestion", id);
    await page.getByRole("button", { name: "Refresh status", exact: true }).click();
    const info = await get(`/v2/ingestion/submissions/${id}`);
    assert.equal(info.jobs.length, spec.children);
    assert.ok(info.jobs.every(job => job.state === "succeeded" && job.attempt_count === 1));
    await expect(page.getByRole("link", { name: "Open catalog and pin this version" }).first()).toBeVisible();
    for (const job of info.jobs) {
      const manifest = await get(`/v2/datasets/${job.result_version}`);
      assert.equal(manifest.source.kind, "official_archive");
      assert.equal(manifest.identity.trade_date, spec.from_date);
      assert.ok(spec.instrument_ids.includes(manifest.instrument.instrument_id));
    }
    Object.assign(receipt, { submission_id: id, versions: info.jobs.map(job => job.result_version) });
  } else if (plan.mode === "canonical") {
    const source = plan.source;
    assert.equal(fs.statSync(source.file_path).size, source.bytes);
    await page.goto(plan.ui_url + "/#/v2/imports/new");
    await page.getByLabel("Instrument", { exact: true }).selectOption(source.metadata.instrument_id);
    await page.getByLabel("Trade UTC date", { exact: true }).fill(source.metadata.trade_date);
    await page.getByRole("combobox").filter({ has: page.locator('option[value="parquet"]') }).selectOption(source.format);
    await page.getByLabel(/^Timestamp encoding/).selectOption(source.metadata.timestamp_encoding);
    await page.getByLabel("Source name", { exact: true }).fill(source.metadata.source_name);
    await page.getByLabel("Source / conversion reference (optional)", { exact: true }).fill(source.metadata.source_reference ?? "");
    await page.getByRole("checkbox", { name: /I confirm this is Binance-origin/ }).check();
    await page.getByLabel("Canonical daily file", { exact: true }).setInputFiles(source.file_path);
    const created = await click("/v2/imports", page.getByRole("button", { name: "Hash and upload canonical file" }));
    const deadline = Date.now() + 1860000;
    let uploaded;
    while (true) {
      uploaded = await get(`/v2/imports/${created.id}`);
      if (["failed", "cancelled", "expired"].includes(uploaded.state)) {
        receipt.import_id = created.id;
        receipt.terminal_upload_state = uploaded.state;
        receipt.received_bytes = uploaded.received_bytes;
        save();
        throw new Error("Canonical upload reached a terminal failure state");
      }
      if (uploaded.state === "uploaded") break;
      assert.ok(Date.now() < deadline, "Canonical upload did not complete within its bound");
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    await expect(page.getByRole("button", { name: "Finalize verified import" })).toBeVisible();
    assert.equal(uploaded.state, "uploaded");
    assert.equal(uploaded.source_sha256, source.sha256);
    assert.equal(uploaded.received_bytes, source.bytes);
    await click(`/v2/imports/${created.id}/finalize`, page.getByRole("button", { name: "Finalize verified import" }));
    const queued = await get(`/v2/imports/${created.id}`);
    worker("ingestion", queued.submission_id);
    await page.getByRole("button", { name: "Refresh import status" }).click();
    const published = await get(`/v2/imports/${created.id}`);
    assert.equal(published.state, "succeeded");
    const manifest = await get(`/v2/datasets/${published.dataset_version_id}`);
    assert.equal(manifest.identity.source_sha256, source.sha256);
    await expect(page.getByRole("link", { name: "Open catalog and pin this version" })).toBeVisible();
    Object.assign(receipt, { import_id: created.id, generation: uploaded.generation, dataset_version: published.dataset_version_id });
  } else if (["model", "model_readback"].includes(plan.mode)) {
    await page.goto(plan.ui_url + "/#/v2/catalog");
    const readback = plan.mode === "model_readback";
    let requestId;
    if (readback) {
      assert.match(plan.readback.request_id, /^[0-9a-f-]{36}$/);
      assert.match(plan.readback.run_id, /^[0-9a-f-]{36}$/);
      requestId = plan.readback.request_id;
    } else {
    // Frozen literal request/spec are supplied by the reviewed Phase 6 input plan.
    const created = await page.evaluate(async body => {
      const response = await fetch("/v2/copilot/requests", {
        method: "POST", redirect: "error", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    }, plan.copilot_request);
    worker("copilot", created.request_id);
    requestId = created.request_id;
    }
    const interpreted = await get(`/v2/copilot/requests/${requestId}`);
    assert.equal(interpreted.outcome, "submitted");
    assert.deepEqual(interpreted.revisions.at(-1).spec, plan.expected_spec);
    assert.equal(interpreted.revisions.at(-1).provenance.model_digest, plan.model_digest);
    const run = interpreted.run_id;
    if (readback) assert.equal(run, plan.readback.run_id);
    Object.assign(receipt, { request_id: requestId, run_id: run, read_only_completion: readback });
    save();
    if (!readback) worker("research", run);
    const numerical = await get(`/v2/research/runs/${run}/results`);
    assert.deepEqual(numerical, plan.expected_results);
    if (!readback) worker("memo", run);
    await page.goto(plan.ui_url + `/#/v2/runs/${run}`);
    await expect(page.locator(".v2-memo-text > p")).toHaveCount(3);
    const memo = await get(`/v2/research/runs/${run}/memo`);
    assert.equal(memo.state, "succeeded");
    assert.ok(memo.model_calls >= 1 && memo.model_calls <= 2);
    assert.equal(memo.provenance.model_digest, plan.model_digest);
    const rendered = (await page.locator(".v2-memo-text > p").allTextContents()).join("\n\n");
    // The application preserves the canonical terminal LF in the last paragraph.
    assert.ok(memo.memo.endsWith("\n") && !memo.memo.endsWith("\n\n"));
    assert.equal(rendered, memo.memo);
    assert.ok(plan.expected_memo_variants.includes(memo.memo));
    Object.assign(receipt, { memo });
  } else throw new Error("Unsupported deferred browser case");
  assert.deepEqual(errors, []);
  receipt.state = "passed";
} catch (error) {
  receipt.state = "failed";
  receipt.error = { name: error.name };
  throw error;
} finally {
  save();
  await page.close();
  await browser.close();
}
