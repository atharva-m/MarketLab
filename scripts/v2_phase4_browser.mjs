// Actual UI/API/worker acceptance. Every child inherits the bootstrap's private Job.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const [role, planFile, folder, configFile] = process.argv.slice(2);
assert.ok(['ui', 'browser'].includes(role));
assert.ok(path.isAbsolute(folder) && path.isAbsolute(planFile));
const nonce = process.env.MARKETLAB_PHASE4_RUN_NONCE;
assert.match(nonce ?? '', /^[a-f0-9]{48}$/);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const stopRequested = () => {
  const file = path.join(folder, role === 'ui' ? 'ui-stop.json' : 'controller-stop.json');
  return fs.existsSync(file) && JSON.parse(fs.readFileSync(file, 'utf8')).nonce === nonce;
};
if (role === 'ui') await runUI();
else await runBrowser();
async function runUI() {
  const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
  const server = await createServer({ root: path.join(root, 'frontend'),
    configFile: path.join(root, 'frontend/vite.config.ts'),
    server: { host: '127.0.0.1', port: 55175, strictPort: true } });
  await server.listen();
  fs.writeFileSync(path.join(folder, 'ui-ready.json'), JSON.stringify({ pid: process.pid, port: 55175 }));
  try { while (!stopRequested()) await sleep(200); }
  finally { await server.close(); fs.writeFileSync(path.join(folder, 'ui-drained.json'), JSON.stringify({ closed: true })); }
}
async function runBrowser() {
const browsers = require('playwright');
const { expect: baseExpect } = require('@playwright/test');
const expect = baseExpect.configure({ timeout: 120_000 });
const plan = JSON.parse(fs.readFileSync(planFile, 'utf8'));
const receiptPath = path.join(folder, 'browser.json');
const receipt = { schema: 'phase4-completion-browser-v1', owner: plan.owner,
  mode: plan.mode, started_utc: new Date().toISOString(), status: 'running',
  engine_results: [], launches: [], events: [], case_events: [], errors: [] };
const save = () => fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2));
const json = (name, body) => fs.writeFileSync(path.join(folder, name), JSON.stringify(body, null, 2));
const uuid = /^[a-f0-9-]{36}$/;
let workerNumber = 0;
let activeBrowser = null;
let stopping = false;
const children = new Map();
const checkStop = () => { if (stopping) throw new Error('Owned browser controller stop requested'); };
const stopTimer = setInterval(() => {
  try {
    if (!stopRequested()) return;
    stopping = true;
    for (const state of children.values()) if (fs.existsSync(state.folder))
      fs.writeFileSync(path.join(state.folder, 'stop.json'), JSON.stringify({ nonce }));
    if (activeBrowser) void activeBrowser.close().catch(error => { receipt.stop_error = error.name; save(); });
  } catch (error) { receipt.stop_error = error.name; save(); }
}, 200);
const caseEvent = (engine, name, phase) => { receipt.case_events.push({ engine, case: name, phase, utc: new Date().toISOString() }); save(); };
save();
async function worker(kind, id, maxJobs = 1) {
  checkStop(); assert.ok(['ingestion', 'research'].includes(kind) && uuid.test(id));
  const workerFolder = path.join(folder, `worker-${++workerNumber}-${kind}-${id}`);
  const args = [path.join(root, 'scripts/v2_phase4_service.py'), 'worker', '--config', configFile,
    '--folder', workerFolder, '--kind', kind, '--target', id, '--max-jobs', String(maxJobs)];
  const log = fs.openSync(`${workerFolder}.log`, 'wx');
  const launch = { role: kind, target: id, argv: [process.env.MARKETLAB_PHASE4_PYTHON, ...args], folder: workerFolder };
  receipt.launches.push(launch); save();
  try {
    const child = spawn(launch.argv[0], args, { cwd: root, env: process.env, windowsHide: true,
      stdio: ['ignore', log, log] });
    const completion = new Promise(resolve => {
      child.once('error', error => resolve({ error_type: error.name }));
      child.once('exit', (code, signal) => resolve({ code, signal }));
    });
    children.set(child, { folder: workerFolder, completion });
    launch.pid = child.pid; save();
    const outcome = await completion; children.delete(child);
    launch.outcome = outcome; save();
    assert.deepEqual(outcome, { code: 0, signal: null }, `Worker failed: ${path.basename(workerFolder)}.log`);
    checkStop();
    const result = JSON.parse(fs.readFileSync(path.join(workerFolder, 'receipt.json'), 'utf8'));
    assert.equal(result.state, 'passed');
    return { receipt: path.relative(root, path.join(workerFolder, 'receipt.json')), ...result };
  } finally { fs.closeSync(log); }
}
async function go(page, route) { checkStop(); await page.goto(`${plan.ui_url}/#${route}`); }
async function read(page, apiPath) {
  checkStop();
  assert.ok(apiPath.startsWith('/v2/'));
  const value = await page.evaluate(async (endpoint) => {
    const response = await fetch(endpoint, { credentials: 'same-origin', redirect: 'error' });
    return { status: response.status, body: await response.json() };
  }, apiPath);
  assert.equal(value.status, 200, `Readback failed ${apiPath}`);
  return value.body;
}
async function postByClick(page, endpoint, button) {
  checkStop();
  receipt.phase = { operation: 'POST by UI click', endpoint }; save();
  // A long valid backend response keeps its existing deadline. A research form
  // which never dispatches fetch is a distinct client-side failure within10s.
  const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === endpoint && response.request().method() === 'POST', { timeout: 1_860_000 });
  const dispatch = endpoint === '/v2/research/runs' ? [page.waitForRequest((request) => new URL(request.url()).pathname === endpoint && request.method() === 'POST', { timeout: 10000 })] : [];
  const [response] = await Promise.all([responsePromise, button.click(), ...dispatch]);
  const value = await response.json();
  assert.ok(response.ok(), `Mutation failed ${endpoint}: ${value?.error?.code ?? response.status()}`);
  return { value, request: response.request().postDataJSON(), status: response.status() };
}
async function register(page, engine) {
  await go(page, '/v2/instruments');
  for (const key of ['source_symbol', 'base_asset', 'quote_asset', 'display_name'])
    await page.getByLabel(key.replaceAll('_', ' '), { exact: true }).fill(plan.registry[key]);
  await page.getByRole('checkbox', { name: /I verified this symbol/ }).check();
  const result = await postByClick(page, '/v2/instruments', page.getByRole('button', { name: 'Register instrument', exact: true }));
  assert.deepEqual(result.request, plan.registry);
  assert.equal(result.value.instrument_id, 'binance:spot:SOLUSDT');
  json(`${engine}-registry.json`, { request: result.request, response: result.value });
}
async function selectedInstrumentRows(group, ids) {
  for (const id of ids) {
    const asset = id.split(':').at(-1).replace(/USDT$/, '');
    await expect(group.getByRole('checkbox', { name: new RegExp(`^${asset}/USDT`) })).toBeVisible();
  }
  for (const asset of ['BTC', 'ETH', 'SOL']) {
    const field = group.getByRole('checkbox', { name: new RegExp(`^${asset}/USDT`) });
    if (await field.count()) await field.setChecked(ids.includes(`binance:spot:${asset}USDT`));
  }
  for (const id of ids) {
    const asset = id.split(':').at(-1).replace(/USDT$/, '');
    await expect(group.getByRole('checkbox', { name: new RegExp(`^${asset}/USDT`) })).toBeChecked();
  }
}
async function official(page, engine) {
  caseEvent(engine, 'official_delivery', 'start');
  const spec = plan.official_by_engine[engine];
  await go(page, '/v2/ingestion/new');
  const group = page.getByRole('group', { name: 'Choose 1\u20132 enabled Binance instruments' });
  await expect(group.getByRole('checkbox', { name: /^SOL\/USDT/ })).toBeVisible();
  await selectedInstrumentRows(group, spec.instrument_ids);
  await page.getByLabel('From UTC date (inclusive)', { exact: true }).fill(spec.from_date);
  await page.getByLabel('Before UTC date (exclusive)', { exact: true }).fill(spec.before_date);
  await page.getByRole('checkbox', { name: /I confirm these instruments and UTC daily boundaries/ }).check();
  const result = await postByClick(page, '/v2/ingestion/submissions', page.getByRole('button', { name: 'Submit official ingestion' }));
  assert.deepEqual(result.request, { schema: 'daily-ingestion-v2', adapter: 'binance_daily', instrument_ids: [...spec.instrument_ids].sort(), from_date: spec.from_date, before_date: spec.before_date });
  const id = result.value.id ?? result.value.submission_id;
  assert.ok(uuid.test(id));
  const executed = await worker('ingestion', id, spec.children);
  await page.getByRole('button', { name: 'Refresh status', exact: true }).click();
  const info = await read(page, `/v2/ingestion/submissions/${id}`);
  assert.equal(info.jobs.length, spec.children);
  assert.ok(info.jobs.every((job) => job.state === 'succeeded' && job.attempt_count === 1));
  const expected = new Set(plan.cases.find((c) => c.name === 'comparison').spec.dataset_versions);
  assert.ok(info.jobs.every((job) => expected.has(job.result_version)));
  await expect(page.getByRole('link', { name: 'Open catalog and pin this version' }).first()).toBeVisible();
  json(`${engine}-official.json`, { request: result.request, response: { id, state: result.value.state }, worker: executed, status: info });
  caseEvent(engine, 'official_delivery', 'fully_asserted_end');
  return { id, jobs: info.jobs };
}

async function canonical(page, engine, source) {
  caseEvent(engine, `${source.format}_delivery`, 'start');
  await go(page, '/v2/imports/new');
  await expect(page.getByLabel('Instrument', { exact: true })).toBeVisible();
  await page.getByLabel('Instrument', { exact: true }).selectOption(source.metadata.instrument_id);
  await page.getByLabel('Trade UTC date', { exact: true }).fill(source.metadata.trade_date);
  const format = page.getByRole('combobox').filter({ has: page.locator('option[value="parquet"]') });
  await format.selectOption(source.format);
  const encoding = page.getByLabel(/^Timestamp encoding/);
  await encoding.selectOption(source.metadata.timestamp_encoding);
  await page.getByLabel('Source name', { exact: true }).fill(source.metadata.source_name);
  await page.getByLabel('Source / conversion reference (optional)', { exact: true }).fill(source.metadata.source_reference ?? '');
  await page.getByRole('checkbox', { name: /I confirm this is Binance-origin/ }).check();
  await page.getByLabel('Canonical daily file', { exact: true }).setInputFiles(source.file_path);
  const created = await postByClick(page, '/v2/imports', page.getByRole('button', { name: 'Hash and upload canonical file' }));
  assert.deepEqual(created.request, { manifest: source.metadata, content_length: source.bytes });
  const id = created.value.id; assert.ok(uuid.test(id));
  // The real API's successful stream transition enforces actual Content-Length,
  // received bytes and SHA-256; this does not rely on WebKit route interception.
  await expect(page.getByRole('button', { name: 'Finalize verified import' })).toBeVisible({ timeout: 1_860_000 });
  const uploaded = await read(page, `/v2/imports/${id}`);
  assert.equal(uploaded.state, 'uploaded');
  assert.equal(uploaded.declared_bytes, source.bytes);
  assert.equal(uploaded.received_bytes, source.bytes);
  assert.equal(uploaded.source_sha256, source.sha256);
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  const token = created.value.upload.required_headers['X-Upload-Token'];
  assert.ok(typeof token === 'string' && token.length >= 32);
  assert.ok(!stored.includes(token), 'Upload capability leaked into browser storage');
  const finalized = await postByClick(page, `/v2/imports/${id}/finalize`, page.getByRole('button', { name: 'Finalize verified import' }));
  assert.deepEqual(finalized.request, { expected_revision: uploaded.revision, generation: uploaded.generation });
  const queued = await read(page, `/v2/imports/${id}`);
  assert.ok(uuid.test(queued.submission_id));
  const executed = await worker('ingestion', queued.submission_id, 1);
  await page.getByRole('button', { name: 'Refresh import status' }).click();
  const published = await read(page, `/v2/imports/${id}`);
  assert.equal(published.state, 'succeeded');
  const specimen = plan.cases.find((c) => c.name === `${source.format}_profile`);
  assert.equal(published.dataset_version_id, specimen.spec.dataset_versions[0]);
  await expect(page.getByRole('link', { name: 'Open catalog and pin this version' })).toBeVisible();
  const manifest = await read(page, `/v2/datasets/${published.dataset_version_id}`);
  assert.equal(manifest.identity.source_sha256, source.sha256);
  assert.equal(manifest.instrument.instrument_id, source.metadata.instrument_id);
  json(`${engine}-${source.format}-import.json`, { request: created.request, create: { id, revision: created.value.revision, generation: created.value.upload.generation, expires_at: created.value.upload.expires_at }, uploaded, finalized: { request: finalized.request, response: finalized.value }, published, manifest, worker: executed });
  caseEvent(engine, `${source.format}_delivery`, 'fully_asserted_end');
  return { id, version: published.dataset_version_id, bytes: source.bytes, source_sha256: source.sha256 };
}

async function pin(page, spec) {
  await go(page, '/v2/catalog');
  await expect(page.getByRole('heading', { name: 'Registered datasets', exact: true })).toBeVisible();
  const clear = page.getByRole('button', { name: 'Clear selection', exact: true });
  if (await clear.count()) await clear.click();
  for (const identity of spec.instrument_ids) {
    await page.getByLabel('Instrument', { exact: true }).selectOption(identity);
    await page.getByLabel('From UTC date (inclusive)', { exact: true }).fill(spec.history_start.slice(0, 10));
    await page.getByLabel('Before UTC date (exclusive)', { exact: true }).fill(spec.end.slice(0, 10));
    const pending = page.waitForResponse((response) => new URL(response.url()).pathname === '/v2/datasets' && response.request().method() === 'GET');
    await page.getByRole('button', { name: 'Filter catalog', exact: true }).click();
    const response = await pending; assert.ok(response.ok());
    const pageData = await response.json();
    assert.equal(pageData.next_cursor, null, 'This frozen small campaign unexpectedly needs catalog pagination');
    for (const version of spec.dataset_versions) {
      const row = pageData.items.find((candidate) => candidate.dataset_version_id === version && candidate.instrument_id === identity);
      if (!row) continue;
      await page.getByRole('checkbox', { name: `Pin ${identity} ${row.trade_date} ${version}`, exact: true }).check();
    }
  }
  await expect(page.getByRole('heading', { name: `Pinned selection \u00b7 ${spec.dataset_versions.length}/62 daily versions` })).toBeVisible();
  await page.getByRole('link', { name: 'Research this selection' }).click();
}
const projection = (body) => Object.fromEntries(Object.entries(body).filter(([key]) => key !== 'instruments'));
async function research(page, engine, specimen) {
  caseEvent(engine, specimen.name, 'start');
  const spec = specimen.spec;
  await pin(page, spec);
  const workflow = page.getByRole('combobox').filter({ has: page.locator('option[value="cross_asset"]') });
  await workflow.selectOption(spec.workflow);
  const group = page.getByRole('group', { name: spec.workflow === 'cross_asset' ? 'Choose exactly two instruments with the same quote asset' : 'Choose one instrument' });
  await selectedInstrumentRows(group, spec.instrument_ids);
  const metadataStatus = page.getByRole('status').filter({ hasText: /Binance spot/ });
  for (const id of spec.instrument_ids) {
    const asset = id.split(':').at(-1).replace(/USDT$/, '');
    await expect(metadataStatus).toContainText(`${asset}/USDT`);
  }
  assert.deepEqual(await page.evaluate(() => JSON.parse(localStorage.getItem('marketlab.v2.research')).instrument_ids.slice().sort()), spec.instrument_ids.slice().sort());
  await page.getByLabel('History start UTC (inclusive)', { exact: true }).fill(spec.history_start);
  await page.getByLabel('Evaluation start UTC (inclusive)', { exact: true }).fill(spec.start);
  await page.getByLabel('Evaluation end UTC (exclusive)', { exact: true }).fill(spec.end);
  const metrics = page.getByRole('group', { name: 'Metrics', exact: true });
  for (const metric of ['profile', 'correlation', 'close_change_difference', 'clusters']) {
    const field = metrics.getByRole('checkbox', { name: metric.replaceAll('_', ' '), exact: true });
    if (await field.count()) await field.setChecked(spec.metrics.includes(metric));
  }
  await page.getByRole('checkbox', { name: /I confirm these exact versions/ }).check();
  const created = await postByClick(page, '/v2/research/runs', page.getByRole('button', { name: 'Submit pinned numerical research', exact: true }));
  assert.deepEqual(created.request, { ...spec, dataset_versions: [...spec.dataset_versions].sort(), instrument_ids: [...spec.instrument_ids].sort(), metrics: [...spec.metrics].sort() });
  const id = created.value.id; assert.ok(uuid.test(id));
  const executed = await worker('research', id, 1);
  await page.getByRole('button', { name: 'Refresh research status', exact: true }).click();
  const status = await read(page, `/v2/research/runs/${id}`);
  assert.equal(status.state, 'succeeded'); assert.equal(status.attempt_count, 1);
  assert.equal(status.memo_available, false);
  assert.deepEqual([...status.spec.dataset_versions].sort(), [...spec.dataset_versions].sort());
  await expect(page.getByRole('heading', { name: 'Verified numerical summary' })).toBeVisible();
  await page.getByRole('button', { name: 'Load full numerical results', exact: true }).click();
  const result = await read(page, `/v2/research/runs/${id}/results`);
  const summary = await read(page, `/v2/research/runs/${id}/summary`);
  assert.deepEqual(projection(result), specimen.expected[0]);
  assert.deepEqual(projection(summary), specimen.expected[1]);
  await page.getByRole('combobox').filter({ has: page.locator('option[value="1m"]') }).selectOption('5m');
  await page.getByRole('combobox').filter({ has: page.locator('option[value="binance:spot:SOLUSDT"]') }).last().selectOption(plan.chart.instrument_id);
  await page.getByLabel('Chart start UTC (inclusive)', { exact: true }).fill(plan.chart.start);
  await page.getByLabel('Chart end UTC (exclusive)', { exact: true }).fill(plan.chart.end);
  const chartResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/v2/bars' && response.request().method() === 'GET', { timeout: 1_860_000 });
  await page.getByRole('button', { name: 'Load pinned chart window', exact: true }).click();
  const response = await chartResponse; assert.ok(response.ok());
  const chart = await response.json();
  assert.deepEqual(chart.bars, plan.chart.expected_bars);
  assert.equal(chart.instrument.instrument_id, plan.chart.instrument_id);
  assert.equal(chart.units.price, 'USDT'); assert.equal(chart.units.base_volume, 'SOL');
  assert.equal(chart.expected_buckets, 12); assert.equal(chart.returned_buckets, 12);
  await expect(page.getByRole('img', { name: /Close price in USDT/ })).toBeVisible();
  assert.ok((await page.locator('.v2-chart').textContent()).includes('UTC'));
  await page.screenshot({ path: path.join(folder, `${engine}-${specimen.name}-chart.png`), fullPage: true });
  json(`${engine}-${specimen.name}-run.json`, { create: { request: created.request, response: created.value }, status, result, summary, chart, worker: executed });
  caseEvent(engine, specimen.name, 'fully_asserted_end');
  return { id, workflow: spec.workflow, specimen: specimen.name, attempt_count: status.attempt_count, exact_numerical_projection: true, exact_independent_bars: true };
}

async function boundary(page) {
  const source = plan.boundary;
  await go(page, '/v2/imports/new');
  await expect(page.getByLabel('Instrument', { exact: true })).toBeVisible();
  await page.getByLabel('Instrument', { exact: true }).selectOption(source.metadata.instrument_id);
  await page.getByLabel('Trade UTC date', { exact: true }).fill(source.metadata.trade_date);
  await page.getByRole('combobox').filter({ has: page.locator('option[value="parquet"]') }).selectOption('csv');
  await page.getByLabel(/^Timestamp encoding/).selectOption(source.metadata.timestamp_encoding);
  await page.getByLabel('Source name', { exact: true }).fill(source.metadata.source_name);
  await page.getByLabel('Source / conversion reference (optional)', { exact: true }).fill(source.metadata.source_reference);
  await page.getByRole('checkbox', { name: /I confirm this is Binance-origin/ }).check();
  await page.getByLabel('Canonical daily file', { exact: true }).setInputFiles(source.over_file_path);
  let overlimitCreates = 0;
  const listen = request => { if (new URL(request.url()).pathname === '/v2/imports' && request.method() === 'POST') overlimitCreates++; };
  page.on('request', listen);
  await page.getByRole('button', { name: 'Hash and upload canonical file' }).click();
  await expect(page.getByRole('alert')).toContainText('at most 4 GiB');
  assert.equal(overlimitCreates, 0, 'Oversize UI attempted an import');
  page.off('request', listen);
  const rejected = await page.evaluate(async body => {
    const response = await fetch('/v2/imports', { method: 'POST', headers: { 'Content-Type': 'application/json',
      'Idempotency-Key': `p4-completion-overlimit-${crypto.randomUUID()}` }, body: JSON.stringify(body) });
    return { status: response.status, body: await response.json() };
  }, { manifest: source.metadata, content_length: 4 * 1024 ** 3 + 1 });
  assert.equal(rejected.status, 422);
  await page.getByLabel('Canonical daily file', { exact: true }).setInputFiles(source.file_path);
  const contentRequest = request => request.method() === 'PUT' &&
    /^\/v2\/imports\/[a-f0-9-]{36}\/content$/.test(new URL(request.url()).pathname);
  const response = page.waitForResponse(value => contentRequest(value.request()), { timeout: 1_860_000 });
  const failed = page.waitForEvent('requestfailed', { predicate: contentRequest, timeout: 1_860_000 })
    .then(request => { throw new Error(`Boundary upload network failure: ${request.failure()?.errorText}`); });
  const transfer = Promise.race([response, failed]);
  // A transport failure can arrive while the UI create-response assertion runs.
  void transfer.catch(() => {});
  const created = await postByClick(page, '/v2/imports', page.getByRole('button', { name: 'Hash and upload canonical file' }));
  assert.deepEqual(created.request, { manifest: source.metadata, content_length: 4 * 1024 ** 3 });
  const uploadedResponse = await transfer;
  assert.ok(uploadedResponse.ok(), `Boundary upload HTTP ${uploadedResponse.status()}`);
  await expect(page.getByRole('button', { name: 'Finalize verified import' })).toBeVisible();
  const uploaded = await read(page, `/v2/imports/${created.value.id}`);
  assert.equal(uploaded.state, 'uploaded'); assert.equal(uploaded.declared_bytes, 4 * 1024 ** 3);
  assert.equal(uploaded.received_bytes, 4 * 1024 ** 3); assert.equal(uploaded.source_sha256, source.sha256);
  const cancelled = await postByClick(page, `/v2/imports/${created.value.id}/cancel`, page.getByRole('button', { name: 'Request durable cancellation', exact: true }));
  const after = await read(page, `/v2/imports/${created.value.id}`);
  assert.equal(after.state, 'cancelled'); assert.equal(after.job_id, null);
  json('boundary.json', { transport_fixture_only: true, canonical_validity_claimed: false,
    normalized_or_published: false, overlimit: rejected, uploaded, cancel: cancelled.value, after });
  return { id: created.value.id, bytes: uploaded.received_bytes, sha256: uploaded.source_sha256,
    state: after.state, transport_fixture_only: true };
}
try {
  for (const engine of plan.engines) {
    checkStop();
    const began = Date.now();
    const result = { engine, started_utc: new Date().toISOString(), status: 'running', imports: [], runs: [] };
    receipt.engine_results.push(result); save();
    const browser = await browsers[engine].launch({ headless: true }); activeBrowser = browser;
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage(); page.setDefaultTimeout(120_000);
    const browserErrors = [];
    page.on('pageerror', error => browserErrors.push({ name: error.name, message: error.message }));
    try {
      if (plan.mode === 'boundary') result.boundary = await boundary(page);
      else if (plan.mode === 'smoke') {
        await go(page, '/v2/catalog');
        await expect(page.getByRole('heading', { name: 'Registered datasets', exact: true })).toBeVisible();
        assert.equal((await read(page, '/v2/capabilities')).auth_mode, 'local');
      } else {
        await register(page, engine);
        result.official = await official(page, engine); save();
        result.runs.push(await research(page, engine, plan.cases.find(c => c.name === 'official_profile'))); save();
        for (const source of plan.canonical) {
          result.imports.push(await canonical(page, engine, source)); save();
          result.runs.push(await research(page, engine, plan.cases.find(c => c.name === `${source.format}_profile`))); save();
        }
        for (const name of ['comparison', 'clusters']) {
          result.runs.push(await research(page, engine, plan.cases.find(c => c.name === name))); save();
        }
      }
      assert.deepEqual(browserErrors, []); result.status = 'passed';
    } catch (error) {
      result.status = 'failed'; result.error = { name: error.name, message: error.message };
      try { await page.screenshot({ path: path.join(folder, `${engine}-failure.png`), fullPage: true }); }
      catch (captureError) { result.capture_error = captureError.name; }
      throw error;
    } finally {
      result.browser_errors = browserErrors;
      await context.close(); await browser.close(); activeBrowser = null;
      result.elapsed_seconds = (Date.now() - began) / 1000; save();
    }
  }
  assert.equal(receipt.engine_results.length, plan.engines.length);
  if (plan.mode === 'actual') {
    assert.equal(receipt.engine_results.reduce((n, v) => n + v.runs.length, 0), 15);
    assert.equal(receipt.engine_results.reduce((n, v) => n + v.imports.length, 0), 6);
    assert.equal(receipt.launches.length, 24);
  }
  receipt.status = 'passed';
} catch (error) {
  for (const result of receipt.engine_results) if (result.status === 'running') {
    result.status = 'failed'; result.error = { name: error.name, message: error.message };
  }
  receipt.status = 'failed'; receipt.errors.push({ name: error.name, message: error.message }); process.exitCode = 1;
} finally {
  clearInterval(stopTimer);
  for (const state of children.values()) if (fs.existsSync(state.folder))
    fs.writeFileSync(path.join(state.folder, 'stop.json'), JSON.stringify({ nonce }));
  if (activeBrowser) await activeBrowser.close();
  await Promise.all([...children.values()].map(value => value.completion));
  receipt.finished_utc = new Date().toISOString(); save();
  console.log(JSON.stringify({ status: receipt.status, mode: plan.mode, engines: receipt.engine_results.map(value => ({
    engine: value.engine, status: value.status, runs: value.runs.length, imports: value.imports.length })) }));
}
}
