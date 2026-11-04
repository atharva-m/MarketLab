// Real UI/API/model flow. Parent launches this process in a held private Job;
// every browser and targeted existing CLI worker inherits that containment.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { createRequire } from "node:module";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { isDeepStrictEqual } from "node:util";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const base = path.join(root, "artifacts", "v2-phase5-20261102");
const require = createRequire(path.join(root, "frontend", "package.json"));
const [role, engine, planFile, folderName, approvalFile, preparedFile] =
  process.argv.slice(2);
assert.ok(["plan", "ui", "browser"].includes(role));
assert.ok(
  role !== "browser"
    ? engine === "none"
    : ["chromium", "firefox", "webkit"].includes(engine),
);
const nonce = process.env.MARKETLAB_P5_OWNED_NONCE;
const sha = (file) => {
  const hash = crypto.createHash("sha256"),
    buffer = Buffer.allocUnsafe(1024 * 1024);
  const handle = fs.openSync(file, "r");
  try {
    for (;;) {
      const size = fs.readSync(handle, buffer);
      if (!size) break;
      hash.update(buffer.subarray(0, size));
    }
    return hash.digest("hex");
  } finally {
    fs.closeSync(handle);
  }
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function makePlan() {
  const boundPath = owned(planFile),
    configPath = owned(approvalFile),
    preparedPath = owned(preparedFile);
  const frozen = read(boundPath);
  assert.equal(sha(configPath), frozen.config_sha256);
  assert.equal(sha(preparedPath), frozen.prepared_sha256);
  assert.equal(read(preparedPath).functional, "passed");
  assert.equal(
    read(path.join(path.dirname(preparedPath), "result.json")).state,
    "passed",
  );
  const example = frozen.bound_fixture.copilot_cases.find(
    (item) => item.id === "clear-first_profile-2",
  );
  const initial = frozen.bound_fixture.clarification_sequences.find(
    (item) => item.id === "A",
  );
  assert.deepEqual(initial.expected_spec, example.expected_spec);
  const metadataPath = path.join(
    path.dirname(require.resolve("playwright-core/package.json")),
    "browsers.json",
  );
  const metadata = read(metadataPath);
  const originalCache = path.join(process.env.LOCALAPPDATA, "ms-playwright");
  const firefoxRoot = path.join(
    root,
    "artifacts",
    "phase5-firefox-20261102-121417",
  );
  const firefoxReceipt = read(path.join(firefoxRoot, "native-version.json"));
  assert.equal(sha(firefoxReceipt.Executable), firefoxReceipt.Sha256);
  assert.equal(firefoxReceipt.FileVersion, "157.0");
  const caches = {
    chromium: originalCache,
    firefox: path.join(firefoxRoot, "browsers"),
    webkit: originalCache,
  };
  for (const value of Object.values(caches))
    assert.ok(fs.statSync(value).isDirectory());
  const coreBundle = path.join(
    path.dirname(require.resolve("playwright-core/package.json")),
    "lib/coreBundle.js",
  );
  const resolverCode = String.raw`
const {registry}=require(process.argv[1]).registry;
const name=process.argv[2]==="chromium"?"chromium-headless-shell":process.argv[2];
console.log(JSON.stringify([name,"ffmpeg","winldd"].map(name=>({name,path:registry.findExecutable(name).executablePath()}))));
`;
  const executableIdentities = {};
  for (const name of ["chromium", "firefox", "webkit"]) {
    const resolved = spawnSync(
      process.execPath,
      ["-e", resolverCode, coreBundle, name],
      {
        cwd: root,
        env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: caches[name] },
        windowsHide: true,
        timeout: 30000,
        maxBuffer: 65536,
        encoding: "utf8",
      },
    );
    assert.ok(
      resolved.status === 0 && !resolved.error,
      "Locked Playwright executable resolution failed",
    );
    const entries = JSON.parse(resolved.stdout).map((item) => ({
      ...item,
      revision: metadata.browsers.find((browser) => browser.name === item.name)
        .revision,
      sha256: sha(item.path),
    }));
    const bundle = path.dirname(entries[0].path);
    const helpers = fs
      .readdirSync(bundle, { withFileTypes: true })
      .filter(
        (item) => item.isFile() && item.name.toLowerCase().endsWith(".exe"),
      );
    assert.ok(
      helpers.length <= 32,
      "Unexpected pinned browser package executable inventory",
    );
    executableIdentities[name] = {
      launcher: entries[0],
      registry_helpers: entries.slice(1),
      package_executables: helpers.map((item) => ({
        path: path.join(bundle, item.name),
        sha256: sha(path.join(bundle, item.name)),
      })),
    };
  }
  const python = path.join(root, ".venv", "Scripts", "python.exe");
  const preflightCode = String.raw`
import json,sys
from marketlab.copilot.v2.model import CopilotModel
from marketlab.memos.v2.model import MemoModel
b=json.load(open(sys.argv[1],encoding="utf-8"))
c=next(x for x in b["bound_fixture"]["copilot_cases"] if x["id"]=="clear-first_profile-2")
s=next(x for x in b["bound_fixture"]["clarification_sequences"] if x["id"]=="A")
a={"schema":"copilot-answer-v2","expected_revision":0,"text":"BTCUSDT","context":c["request"]["context"]}
r=next(x for x in b["memo_runs"]["A"] if x["expected_spec"]==c["expected_spec"])
m=CopilotModel("http://127.0.0.1:1")
print(json.dumps({"initial":m.prepare(s["snapshot"],[s["request"]]),"answer":m.prepare(s["snapshot"],[s["request"],a]),"memo":MemoModel("http://127.0.0.1:1").prepare(r["facts"])}))
`;
  const checked = spawnSync(python, ["-B", "-c", preflightCode, boundPath], {
    cwd: root,
    env: { ...process.env, PYTHONPATH: path.join(root, "src") },
    windowsHide: true,
    timeout: 30000,
    maxBuffer: 65536,
    encoding: "utf8",
  });
  assert.ok(
    checked.status === 0 && !checked.error,
    "Offline browser input preflight failed; no inference permitted",
  );
  const preflights = JSON.parse(checked.stdout);
  assert.ok(
    Object.values(preflights).every((item) => item.input_bytes <= 6000),
  );
  const output = owned(folderName);
  assert.ok(!fs.existsSync(output));
  fs.mkdirSync(output);
  const draft = {
    schema: "phase5-actual-browser-plan-v1",
    owner: "v2-phase5-20261102",
    status: "draft_requires_independent_exact_browser_review",
    engines: ["chromium", "firefox", "webkit"],
    ui_url: "http://127.0.0.1:58184",
    api_url: "http://127.0.0.1:58185",
    bound_path: boundPath,
    bound_sha256: sha(boundPath),
    config_path: configPath,
    config_sha256: sha(configPath),
    prepared_folder: path.dirname(preparedPath),
    python,
    python_sha256: sha(python),
    playwright_version: require("playwright/package.json").version,
    browser_metadata_sha256: sha(metadataPath),
    browser_cache_roots: caches,
    executable_identities: executableIdentities,
    expected_browser_versions: Object.fromEntries(
      ["chromium", "firefox", "webkit"].map((name) => [
        name,
        metadata.browsers.find((item) => item.name === name).browserVersion,
      ]),
    ),
    ui_source_files: sourceFiles(),
    initial_request: initial.request,
    answer: {
      schema: "copilot-answer-v2",
      expected_revision: 0,
      text: "BTCUSDT",
      context: example.request.context,
    },
    manual_spec: example.expected_spec,
    model_preflights: preflights,
    call_budget: {
      requests_per_engine: 1,
      accepted_answers_per_request: 1,
      memo_jobs_per_engine: 1,
      expected_native_responses_per_engine: 3,
      maximum_reserved_calls_per_engine: 6,
      scored_cohort_credit: false,
    },
    launch: {
      lifecycle_helper: "scripts/v2_phase4_lifecycle.py:OwnedJob",
      before_resume_containment: true,
      held_handles_and_birth: true,
      engines_sequential: true,
      sample_seconds: 0.5,
      maximum_sample_gap_seconds: 1,
      api_port: 58185,
      ui_port: 58184,
      phase5_environment_flag: "MARKETLAB_PHASE5_TEST=1",
      cooperative_stop:
        "stop scheduling; close UI/browser; wait for already bounded targeted CLI workers; parent verifies private Job drain; any forced termination fails lifecycle",
      worker_outer_seconds: 2160,
    },
    qualification:
      "Real browser/API/targeted pinned-model workers only. No route interception, no bound40 memo consumption, no scored cohort credit. Optional missing-old-memo enqueue button retains separate mocked UI plus actual P5-02 endpoint/durable evidence; not actual browser enqueue credit.",
    inference_approval:
      "Independent exact prompt/answer/selection/byte-budget/source/launch review required before native model dispatch; maximum18 reserved calls across three engines.",
  };
  const target = path.join(output, "browser-plan.json");
  write(target, draft);
  fs.writeSync(
    1,
    JSON.stringify({
      status: draft.status,
      plan: target,
      sha256: sha(target),
      model_operations: 0,
    }) + "\n",
  );
}
function owned(file) {
  assert.ok(path.isAbsolute(file));
  const resolved = path.resolve(file);
  assert.ok(resolved.startsWith(base + path.sep) && resolved !== base);
  for (
    let current = resolved;
    current !== path.dirname(current);
    current = path.dirname(current)
  )
    if (fs.existsSync(current))
      assert.ok(
        !fs.lstatSync(current).isSymbolicLink(),
        "Owned evidence path has a link",
      );
  return resolved;
}
function read(file) {
  assert.ok(fs.statSync(file).size <= 16 * 1024 ** 2);
  return JSON.parse(fs.readFileSync(file, "utf8"));
}
function write(file, body) {
  owned(file);
  const raw = JSON.stringify(body, null, 2) + "\n";
  assert.ok(Buffer.byteLength(raw) <= 16 * 1024 ** 2);
  const temporary = file + ".tmp";
  fs.writeFileSync(temporary, raw);
  fs.renameSync(temporary, file);
}
function sourceFiles() {
  const names = [
    "scripts/v2_phase5_browser.mjs",
    "frontend/vite.config.ts",
    "frontend/package.json",
    "frontend/package-lock.json",
  ];
  function visit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      assert.ok(!entry.isSymbolicLink());
      if (entry.isDirectory()) visit(file);
      else if (entry.isFile())
        names.push(path.relative(root, file).split(path.sep).join("/"));
    }
  }
  visit(path.join(root, "frontend", "src"));
  return Object.fromEntries(
    names.sort().map((name) => [name, sha(path.join(root, name))]),
  );
}
if (role === "plan") {
  makePlan();
  process.exit(0);
}
assert.match(nonce ?? "", /^[a-f0-9]{32}$/);
const plan = read(owned(planFile));
const approval = read(owned(approvalFile));
assert.equal(plan.schema, "phase5-actual-browser-plan-v1");
assert.equal(plan.owner, "v2-phase5-20261102");
assert.deepEqual(plan.engines, ["chromium", "firefox", "webkit"]);
assert.equal(plan.ui_url, "http://127.0.0.1:58184");
assert.equal(plan.api_url, "http://127.0.0.1:58185");
assert.equal(approval.schema, "phase5-browser-independent-approval-v1");
assert.equal(approval.reviewer, "gpt-6-astra/medium");
assert.equal(approval.outcome, "passed");
assert.equal(approval.plan_sha256, sha(planFile));
assert.deepEqual(plan.ui_source_files, sourceFiles());
assert.equal(approval.driver_sha256, sha(fileURLToPath(import.meta.url)));
assert.equal(
  approval.vite_sha256,
  sha(path.join(root, "frontend/vite.config.ts")),
);
assert.equal(sha(owned(plan.bound_path)), plan.bound_sha256);
assert.equal(sha(owned(plan.config_path)), plan.config_sha256);
assert.equal(approval.bound_sha256, plan.bound_sha256);
assert.equal(approval.config_sha256, plan.config_sha256);
assert.ok(
  Array.isArray(approval.allowed_engines) &&
    new Set(approval.allowed_engines).size === approval.allowed_engines.length,
);
assert.ok(
  approval.allowed_engines.length >= 1 &&
    approval.allowed_engines.every((name) => plan.engines.includes(name)),
);
assert.ok(
  Number.isSafeInteger(approval.prior_reserved_calls) &&
    approval.prior_reserved_calls >= 0,
);
const continuation = plan.chromium_resume;
assert.equal(approval.prior_reserved_calls, continuation ? 1 : 0);
assert.equal(
  approval.maximum_new_reserved_calls,
  approval.allowed_engines.length * 6 - approval.prior_reserved_calls,
);
assert.ok(
  approval.prior_reserved_calls + approval.maximum_new_reserved_calls <= 18,
  "Parent aggregate browser budget exceeded",
);
if (role === "browser")
  assert.ok(
    approval.allowed_engines.includes(engine),
    "Engine is not authorized by this invocation ledger",
  );
if (approval.prior_reserved_calls > 0) {
  assert.ok(
    approval.prior_invocation_receipts?.length > 0,
    "Retry requires retained prior call-accounting receipts",
  );
  for (const prior of approval.prior_invocation_receipts)
    assert.equal(sha(owned(prior.path)), prior.sha256);
}
const bound = read(plan.bound_path);
for (const [name, expected] of Object.entries(bound.source_files)) {
  const file = path.resolve(root, name);
  assert.ok(file.startsWith(root + path.sep));
  assert.equal(sha(file), expected, `Frozen runtime source changed: ${name}`);
}
const candidate = bound.bound_fixture.copilot_cases.find(
  (item) => item.id === "clear-first_profile-2",
);
const sequence = bound.bound_fixture.clarification_sequences.find(
  (item) => item.id === "A",
);
assert.deepEqual(sequence.expected_spec, candidate.expected_spec);
assert.deepEqual(plan.initial_request, sequence.request);
assert.deepEqual(plan.answer, {
  schema: "copilot-answer-v2",
  expected_revision: 0,
  text: "BTCUSDT",
  context: candidate.request.context,
});
assert.deepEqual(plan.manual_spec, candidate.expected_spec);
assert.deepEqual(plan.call_budget, {
  requests_per_engine: 1,
  accepted_answers_per_request: 1,
  memo_jobs_per_engine: 1,
  expected_native_responses_per_engine: 3,
  maximum_reserved_calls_per_engine: 6,
  scored_cohort_credit: false,
});
const reference = bound.memo_runs.A.find((item) =>
  isDeepStrictEqual(item.expected_spec, candidate.expected_spec),
);
assert.ok(reference, "Exact precomputed numerical reference required");
const expectedResultsFile = owned(
  path.join(plan.prepared_folder, `${reference.run_id}-results.json`),
);
assert.equal(
  sha(expectedResultsFile),
  reference.numerical_evidence.hashes.results,
);
const expectedResults = read(expectedResultsFile);
const config = read(plan.config_path);
assert.equal(config.owner, plan.owner);
assert.equal(config.api_url, plan.api_url);
assert.equal(
  path.resolve(process.env.MARKETLAB_STORAGE_PATH ?? ""),
  path.resolve(config.storage_path),
);
assert.equal(process.env.MARKETLAB_REDIS_URL, config.redis_url);
assert.equal(process.env.MARKETLAB_OLLAMA_URL, config.ollama_url);
assert.equal(process.env.MARKETLAB_COPILOT_MODEL, bound.protocols.model);
assert.equal(
  process.env.MARKETLAB_COPILOT_MODEL_DIGEST,
  bound.protocols.model_digest,
);
const privateConfig = read(owned(config.postgres_receipt));
assert.equal(
  path.resolve(plan.python),
  path.join(root, ".venv", "Scripts", "python.exe"),
);
assert.equal(sha(plan.python), plan.python_sha256);
// Never put credential-bearing values into assertion diagnostics or receipts.
assert.ok(
  process.env.MARKETLAB_DATABASE_PASSWORD === privateConfig.password,
  "Owned worker password differs",
);
let database;
try {
  database = new URL(process.env.MARKETLAB_DATABASE_URL);
} catch {
  throw new Error("Owned database environment URL is malformed");
}
assert.ok(
  database.hostname === "127.0.0.1" &&
    database.port === "55485" &&
    database.pathname === "/" + config.database_name &&
    database.username === "phase5",
  "Owned worker database endpoint differs",
);
const folder = owned(folderName);
assert.ok(
  !fs.existsSync(folder),
  "Fresh named browser evidence folder required",
);
fs.mkdirSync(folder);
const stopRequested = () => {
  const file = path.join(path.dirname(folder), "controller-stop.json");
  try {
    return fs.existsSync(file) && read(file).nonce === nonce;
  } catch {
    return false;
  } // A stop is acted on only after its complete owned nonce is readable.
};
if (role === "ui") await ui();
else await browserFlow();

async function ui() {
  assert.equal(process.env.MARKETLAB_PHASE5_TEST, "1");
  const { createServer } = await import(
    pathToFileURL(require.resolve("vite")).href
  );
  const server = await createServer({
    root: path.join(root, "frontend"),
    configFile: path.join(root, "frontend/vite.config.ts"),
  });
  assert.equal(server.config.server.port, 58184);
  await server.listen();
  write(path.join(folder, "ui-ready.json"), {
    pid: process.pid,
    port: 58184,
    plan_sha256: sha(planFile),
  });
  try {
    while (!stopRequested()) await sleep(200);
  } finally {
    await server.close();
    write(path.join(folder, "ui-drained.json"), {
      closed: true,
      stopped_utc: new Date().toISOString(),
    });
  }
}

async function browserFlow() {
  const resume = engine === "chromium" ? continuation : undefined;
  const priorCalls = resume ? 1 : 0;
  const cold = approval.cold_worker;
  assert.equal(cold.ollama_url, "http://127.0.0.1:11435");
  assert.equal(sha(owned(cold.command_path)), cold.command_sha256);
  assert.equal(sha(owned(cold.plan_path)), cold.plan_sha256);
  const coldWorker = read(cold.command_path).python;
  assert.ok(typeof coldWorker === "string" && coldWorker.length <= 16384);
  process.env.PLAYWRIGHT_BROWSERS_PATH = plan.browser_cache_roots[engine];
  assert.ok(path.isAbsolute(process.env.PLAYWRIGHT_BROWSERS_PATH));
  const browsers = require("playwright");
  const { expect: originalExpect } = require("@playwright/test");
  const expect = originalExpect.configure({ timeout: 120000 });
  const metadataPath = path.join(
    path.dirname(require.resolve("playwright-core/package.json")),
    "browsers.json",
  );
  assert.equal(sha(metadataPath), plan.browser_metadata_sha256);
  assert.equal(
    require("playwright/package.json").version,
    plan.playwright_version,
  );
  const browserMetadata = read(metadataPath).browsers.find(
    (item) => item.name === engine,
  );
  assert.equal(
    plan.expected_browser_versions[engine],
    browserMetadata.browserVersion,
  );
  const receipt = {
    schema: "phase5-actual-browser-result-v1",
    engine,
    owner: plan.owner,
    started_utc: new Date().toISOString(),
    status: "running",
    route_interception: false,
    scored_cohort_credit: false,
    launches: [],
    mutations: [],
    stages: [],
    errors: [],
    observed_posts: [],
    prior_reserved_model_calls: priorCalls,
  };
  const save = () => write(path.join(folder, "browser.json"), receipt);
  const stage = (name) => {
    receipt.stages.push({ name, utc: new Date().toISOString() });
    save();
  };
  const children = new Set();
  let stopping = false;
  let browser;
  let context;
  let number = 0;
  let slotPath;
  let slot;
  let slotOwned = false;
  const checkStop = () => {
    if (stopping) throw new Error("Owned browser stop requested");
  };
  const timer = setInterval(() => {
    if (!stopRequested()) return;
    stopping = true;
    if (browser)
      void browser.close().catch((error) => {
        receipt.stop_error = error.name;
        save();
      });
  }, 200);
  async function get(page, endpoint) {
    checkStop();
    const result = await page.evaluate(async (url) => {
      const response = await fetch(url, {
        credentials: "same-origin",
        redirect: "error",
      });
      const text = await response.text();
      if (text.length > 16 * 1024 ** 2)
        throw new Error("Bounded actual response exceeded");
      return { status: response.status, data: JSON.parse(text) };
    }, endpoint);
    assert.equal(result.status, 200, `Actual GET failed: ${endpoint}`);
    return result.data;
  }
  async function clickPost(page, endpoint, button) {
    checkStop();
    const pending = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === endpoint &&
        response.request().method() === "POST",
      { timeout: 1860000 },
    );
    await button.click();
    const response = await pending;
    const body = await response.json();
    assert.ok(
      response.ok(),
      `Actual UI mutation failed: ${endpoint} ${body.error?.code ?? response.status()}`,
    );
    const record = {
      endpoint,
      body: response.request().postDataJSON(),
      operation_key: response.request().headers()["idempotency-key"],
      status: response.status(),
      response: body,
    };
    receipt.mutations.push(record);
    save();
    return record;
  }
  async function worker(kind, identity) {
    assert.match(identity, /^[a-f0-9-]{36}$/);
    const module = {
      copilot: "marketlab.copilot_cli",
      memo: "marketlab.memo_cli",
      research: "marketlab.research_cli",
    }[kind];
    assert.ok(module);
    for (let attempt = 0; attempt < 3; attempt++) {
      checkStop();
      const endpoint =
        kind === "copilot"
          ? `/v2/copilot/requests/${identity}`
          : `/v2/research/runs/${identity}${kind === "memo" ? "/memo" : ""}`;
      const before = await get(page, endpoint);
      if (["succeeded", "failed", "cancelled"].includes(before.state))
        return before;
      const workerArgs = [
        "v2",
        "worker",
        kind === "research" ? "--max-runs" : "--max-jobs",
        "1",
        kind === "copilot" ? "--request" : "--run",
        identity,
        "--wait-seconds",
        "120",
      ];
      const args =
        kind === "research"
          ? ["-B", "-m", module, ...workerArgs]
          : [
              "-B",
              "-c",
              coldWorker,
              cold.plan_path,
              cold.plan_sha256,
              folder,
              module,
              ...workerArgs,
            ];
      const log = fs.openSync(
        path.join(folder, `worker-${++number}-${kind}.log`),
        "wx",
      );
      const launch = {
        kind,
        identity,
        argv: [plan.python, ...args],
        started_utc: new Date().toISOString(),
      };
      receipt.launches.push(launch);
      save();
      try {
        const child = spawn(plan.python, args, {
          cwd: root,
          env:
            kind === "research"
              ? process.env
              : { ...process.env, MARKETLAB_OLLAMA_URL: cold.ollama_url },
          windowsHide: true,
          stdio: ["ignore", log, log],
        });
        const complete = new Promise((resolve) => {
          child.once("error", (error) => resolve({ error_type: error.name }));
          child.once("exit", (code, signal) => resolve({ code, signal }));
        });
        children.add(complete);
        launch.pid = child.pid;
        save();
        let deadline;
        const timedOut = new Promise((resolve) => {
          deadline = setTimeout(() => resolve({ timed_out: true }), 2160000);
        });
        const outcome = await Promise.race([complete, timedOut]);
        clearTimeout(deadline);
        launch.outcome = outcome;
        launch.ended_utc = new Date().toISOString();
        save();
        if (outcome.timed_out) {
          write(path.join(path.dirname(folder), "controller-stop.json"), {
            nonce,
            reason: "Existing bounded CLI worker exceeded outer2160s deadline",
          });
          throw new Error(
            "Targeted worker deadline exceeded; parent held Job must verify drain",
          );
        }
        children.delete(complete);
        assert.deepEqual(outcome, { code: 0, signal: null });
      } finally {
        fs.closeSync(log);
      }
    }
    const endpoint =
      kind === "copilot"
        ? `/v2/copilot/requests/${identity}`
        : `/v2/research/runs/${identity}${kind === "memo" ? "/memo" : ""}`;
    const final = await get(page, endpoint);
    if (["succeeded", "failed", "cancelled"].includes(final.state))
      return final;
    throw new Error(
      "Targeted worker did not reach terminal state within three invocations",
    );
  }
  async function fillContext(page, value) {
    const details = page.locator("details").filter({
      has: page.getByText("Optional explicit structured context", {
        exact: true,
      }),
    });
    await details.locator("summary").click();
    if (value.workflow)
      await details
        .locator("label:has(> select)")
        .filter({ hasText: /^\s*Context workflow/ })
        .locator(":scope > select")
        .selectOption(value.workflow);
    if (value.interval)
      await details
        .locator("label:has(> select)")
        .filter({ hasText: /^\s*Context interval/ })
        .locator(":scope > select")
        .selectOption(value.interval);
    for (const [field, title] of [
      ["history_start", "Context history start UTC (inclusive)"],
      ["start", "Context evaluation start UTC (inclusive)"],
      ["end", "Context evaluation end UTC (exclusive)"],
    ])
      if (value[field])
        await details.getByLabel(title, { exact: true }).fill(value[field]);
    for (const identity of value.instrument_ids ?? [])
      await details
        .getByRole("group", {
          name: "Context instruments (optional subset)",
          exact: true,
        })
        .getByRole("checkbox", { name: identity, exact: true })
        .check();
    for (const metric of value.metrics ?? [])
      await details
        .getByRole("group", { name: "Context metrics (optional)", exact: true })
        .getByRole("checkbox", { name: metric, exact: true })
        .check();
  }
  async function pin(page) {
    await page.goto(plan.ui_url + "/#/v2/catalog");
    const spec = plan.manual_spec;
    const before = new Date(
      Math.floor((Date.parse(spec.end) - 1) / 86400000) * 86400000 + 86400000,
    )
      .toISOString()
      .slice(0, 10);
    for (const identity of spec.instrument_ids) {
      await page
        .getByLabel("Instrument", { exact: true })
        .selectOption(identity);
      await page
        .getByLabel("From UTC date (inclusive)", { exact: true })
        .fill(spec.history_start.slice(0, 10));
      await page
        .getByLabel("Before UTC date (exclusive)", { exact: true })
        .fill(before);
      const pending = page.waitForResponse((response) => {
        const url = new URL(response.url());
        return (
          url.pathname === "/v2/datasets" &&
          url.searchParams.get("instrument_id") === identity &&
          url.searchParams.get("before_date") === before
        );
      });
      await page
        .getByRole("button", { name: "Filter catalog", exact: true })
        .click();
      const response = await pending;
      assert.ok(response.ok());
      const body = await response.json();
      assert.equal(body.next_cursor, null);
      for (const version of spec.dataset_versions) {
        const row = body.items.find(
          (item) =>
            item.dataset_version_id === version &&
            item.instrument_id === identity,
        );
        if (row)
          await page
            .getByRole("checkbox", {
              name: `Pin ${identity} ${row.trade_date} ${version}`,
              exact: true,
            })
            .check();
      }
    }
    await expect(
      page.getByRole("heading", {
        name: `Pinned selection · ${spec.dataset_versions.length}/62 daily versions`,
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("link", {
        name: "Ask copilot about this selection",
        exact: true,
      })
      .click();
  }
  async function compareNumerical(page, id) {
    const summary = await get(page, `/v2/research/runs/${id}/summary`);
    const results = await get(page, `/v2/research/runs/${id}/results`);
    assert.deepEqual(summary, reference.summary);
    assert.deepEqual(results, expectedResults);
    return {
      summary_sha256: reference.summary_sha256,
      results_sha256: reference.numerical_evidence.hashes.results,
    };
  }
  function verifyModelReceipt(info, expected, kind) {
    assert.ok(info.model_calls >= 1 && info.model_calls <= 2);
    assert.equal(info.calls.length, info.model_calls);
    for (const call of info.calls) {
      assert.equal(call.input_sha256, expected.input_sha256);
      assert.equal(call.model_digest, bound.protocols.model_digest);
    }
    for (const key of ["input_sha256", "schema_sha256", "prompt_sha256"])
      assert.equal(info.provenance[key], expected[key]);
    assert.equal(info.provenance.model_digest, bound.protocols.model_digest);
    assert.equal(info.provenance.think, false);
    assert.deepEqual(info.provenance.settings, {
      temperature: 0,
      num_ctx: 8192,
      num_predict: kind === "copilot" ? -1 : 2048,
    });
  }
  let page;
  try {
    save();
    const ledgerFolder = owned(
      path.join(base, "browser-invocations", sha(planFile)),
    );
    fs.mkdirSync(ledgerFolder, { recursive: true });
    slotPath = path.join(ledgerFolder, `${engine}.json`);
    slot = {
      schema: "phase5-browser-invocation-slot-v1",
      engine,
      plan_sha256: sha(planFile),
      approval_sha256: sha(approvalFile),
      output_folder: folder,
      pid: process.pid,
      started_utc: new Date().toISOString(),
      reserved_upper_bound: 6 - priorCalls,
      actual_reserved_calls: null,
      status: "running",
      retry_policy:
        "No second engine invocation under this plan; revised approval must retain all spent/unknown calls within aggregate18",
    };
    const exclusive = fs.openSync(slotPath, "wx");
    try {
      fs.writeSync(exclusive, JSON.stringify(slot) + "\n");
      slotOwned = true;
    } finally {
      fs.closeSync(exclusive);
    }
    const identity = plan.executable_identities[engine];
    for (const item of [
      identity.launcher,
      ...identity.registry_helpers,
      ...identity.package_executables,
    ])
      assert.equal(
        sha(item.path),
        item.sha256,
        "Approved browser executable/helper bytes changed",
      );
    receipt.executable_identity = identity;
    stage("native_browser_launch");
    browser = await browsers[engine].launch({
      headless: true,
      executablePath: identity.launcher.path,
    });
    receipt.browser_version = browser.version();
    assert.equal(
      receipt.browser_version,
      plan.expected_browser_versions[engine],
    );
    context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    });
    await context.tracing.start({
      screenshots: true,
      snapshots: true,
      sources: true,
    });
    page = await context.newPage();
    page.setDefaultTimeout(120000);
    page.on("request", (request) => {
      const endpoint = new URL(request.url()).pathname;
      if (request.method() === "POST" && endpoint.startsWith("/v2/")) {
        receipt.observed_posts.push({
          endpoint,
          operation_key: request.headers()["idempotency-key"],
          body_sha256: crypto
            .createHash("sha256")
            .update(request.postData() ?? "")
            .digest("hex"),
        });
        save();
      }
    });
    const pageErrors = [];
    page.on("pageerror", (error) =>
      pageErrors.push({ name: error.name, message: error.message }),
    );
    const unexpectedDialogs = [];
    page.on("dialog", (dialog) => {
      unexpectedDialogs.push(dialog.message());
      void dialog.dismiss();
    });
    await pin(page);
    stage("catalog_pins_confirmed");
    let requestId;
    let clarified;
    if (resume) {
      for (const ref of [resume.browser, resume.audit]) {
        assert.ok(approval.prior_invocation_receipts.some(
          (prior) => prior.path === ref.path && prior.sha256 === ref.sha256,
        ));
      }
      const earlier = read(owned(resume.browser.path));
      const audit = read(owned(resume.audit.path));
      requestId = resume.request_id;
      assert.match(requestId, /^[a-f0-9-]{36}$/);
      assert.equal(earlier.engine, "chromium");
      assert.equal(earlier.status, "failed");
      assert.equal(earlier.request_id, requestId);
      assert.equal(audit.request_id, requestId);
      assert.equal(earlier.mutations.length, 1);
      assert.equal(earlier.observed_posts.length, 1);
      assert.equal(earlier.mutations[0].endpoint, "/v2/copilot/requests");
      assert.equal(earlier.mutations[0].response.request_id, requestId);
      assert.deepEqual(earlier.mutations[0].body, plan.initial_request);
      assert.equal(earlier.launches.length, 1);
      assert.deepEqual(earlier.launches[0].outcome, { code: 0, signal: null });
      assert.equal(earlier.stages.at(-1).name, "actual_questions_visible");
      assert.equal(audit.status.current_revision, 0);
      assert.equal(audit.status.revisions.length, 1);
      assert.equal(audit.status.revisions[0].model_calls, priorCalls);
      assert.equal(audit.ledger.handoffs, 0);
      assert.equal(audit.ledger.calls.length, priorCalls);
      assert.equal(audit.ledger.calls[0].state, "checkpointed");
      assert.deepEqual(earlier.questions, audit.status.revisions[0].questions);
      const publicStatus = structuredClone(audit.status);
      delete publicStatus.revisions[0].provenance.response;
      await page.goto(`${plan.ui_url}/#/v2/copilot/${requestId}`);
      clarified = await get(page, `/v2/copilot/requests/${requestId}`);
      assert.deepEqual(clarified, publicStatus);
      assert.equal(receipt.observed_posts.length, 0);
      receipt.mutations = earlier.mutations;
      receipt.observed_posts = earlier.observed_posts;
      receipt.retained_initial_chromium = resume;
      stage("original_chromium_request_recovered");
    } else {
      await page
        .getByLabel("Research request", { exact: true })
        .fill(plan.initial_request.text);
      await fillContext(page, plan.initial_request.context);
      await page
        .getByRole("checkbox", {
          name: /I confirm these exact selected versions/,
        })
        .check();
      const created = await clickPost(
        page,
        "/v2/copilot/requests",
        page.getByRole("button", {
          name: "Submit selected-context request",
          exact: true,
        }),
      );
      assert.deepEqual(created.body, plan.initial_request);
      requestId = created.response.request_id;
      receipt.request_id = requestId;
      save();
      await expect(page).toHaveURL(new RegExp(`/v2/copilot/${requestId}$`));
      await page.reload();
      await expect(
        page.getByRole("button", { name: "Refresh copilot status", exact: true }),
      ).toBeVisible();
      assert.equal(receipt.mutations.length, 1);
      assert.equal(receipt.observed_posts.length, 1);
      stage("durable_request_recovered");
      clarified = await worker("copilot", requestId);
    }
    receipt.request_id = requestId;
    assert.equal(clarified.outcome, "needs_clarification");
    verifyModelReceipt(
      clarified.revisions[0],
      plan.model_preflights.initial,
      "copilot",
    );
    assert.ok(
      clarified.revisions[0].model_calls >= 1 &&
        clarified.revisions[0].model_calls <= 2,
    );
    await page
      .getByRole("button", { name: "Refresh copilot status", exact: true })
      .click();
    await expect(
      page.getByLabel("Clarification answer", { exact: true }),
    ).toBeVisible();
    for (const question of clarified.revisions[0].questions)
      await expect(
        page.getByText(`${question.field}: ${question.question}`, {
          exact: true,
        }),
      ).toBeVisible();
    receipt.questions = clarified.revisions[0].questions;
    save();
    stage("actual_questions_visible");
    await page
      .getByLabel("Clarification answer", { exact: true })
      .fill(plan.answer.text);
    await fillContext(page, plan.answer.context);
    const answer = await clickPost(
      page,
      `/v2/copilot/requests/${requestId}/clarifications`,
      page.getByRole("button", {
        name: "Submit clarification answer",
        exact: true,
      }),
    );
    assert.deepEqual(answer.body, plan.answer);
    const submitted = await worker("copilot", requestId);
    assert.equal(submitted.outcome, "submitted");
    assert.equal(submitted.current_revision, 1);
    verifyModelReceipt(
      submitted.revisions[1],
      plan.model_preflights.answer,
      "copilot",
    );
    assert.deepEqual(submitted.revisions[1].spec, plan.manual_spec);
    receipt.copilot_status = submitted;
    save();
    await page
      .getByRole("button", { name: "Refresh copilot status", exact: true })
      .click();
    await page
      .getByRole("link", { name: "Open linked numerical result", exact: true })
      .click();
    const runId = submitted.run_id;
    assert.match(runId, /^[a-f0-9-]{36}$/);
    const numerical = await worker("research", runId);
    assert.equal(numerical.state, "succeeded");
    await page
      .getByRole("button", { name: "Refresh research status", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Verified numerical summary",
        exact: true,
      }),
    ).toBeVisible();
    receipt.copilot_numerical = await compareNumerical(page, runId);
    const pendingMemo = await get(page, `/v2/research/runs/${runId}/memo`);
    assert.equal(pendingMemo.state, "queued");
    assert.equal(pendingMemo.model_calls, 0);
    stage("numerical_available_while_memo_pending");
    await page.goto(plan.ui_url + "/#/v2/research/new");
    await page
      .locator("label:has(> select)")
      .filter({ hasText: /^\s*Workflow/ })
      .locator(":scope > select")
      .selectOption(plan.manual_spec.workflow);
    await page
      .getByLabel("History start UTC (inclusive)", { exact: true })
      .fill(plan.manual_spec.history_start);
    await page
      .getByLabel("Evaluation start UTC (inclusive)", { exact: true })
      .fill(plan.manual_spec.start);
    await page
      .getByLabel("Evaluation end UTC (exclusive)", { exact: true })
      .fill(plan.manual_spec.end);
    await page
      .getByRole("checkbox", {
        name: /I confirm these exact versions, UTC boundaries/,
      })
      .check();
    const manual = await clickPost(
      page,
      "/v2/research/runs",
      page.getByRole("button", {
        name: "Submit pinned numerical research",
        exact: true,
      }),
    );
    assert.deepEqual(manual.body, plan.manual_spec);
    const manualId = manual.response.id;
    const manualStatus = await worker("research", manualId);
    assert.equal(manualStatus.state, "succeeded");
    await page
      .getByRole("button", { name: "Refresh research status", exact: true })
      .click();
    receipt.manual_run_id = manualId;
    receipt.manual_numerical = await compareNumerical(page, manualId);
    assert.equal(
      (await get(page, `/v2/research/runs/${runId}/memo`)).model_calls,
      0,
    );
    stage("manual_numerical_independence_confirmed");
    const finishedMemo = await worker("memo", runId);
    assert.equal(finishedMemo.state, "succeeded");
    verifyModelReceipt(finishedMemo, plan.model_preflights.memo, "memo");
    assert.ok(reference.expected_memo_variants.includes(finishedMemo.memo));
    await page.goto(`${plan.ui_url}/#/v2/runs/${runId}`);
    await expect(page.locator(".v2-memo-text > p")).toHaveCount(3);
    assert.equal(
      (await page.locator(".v2-memo-text > p").allTextContents()).join("\n\n"),
      finishedMemo.memo,
    );
    await expect(
      page.locator(
        ".v2-memo-text script, .v2-memo-text strong, .v2-memo-text iframe",
      ),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "Pinned dataset charts", exact: true }),
    ).toBeVisible();
    await page.reload();
    await expect(page.locator(".v2-memo-text > p")).toHaveCount(3);
    receipt.memo_status = finishedMemo;
    assert.deepEqual(pageErrors, []);
    assert.deepEqual(unexpectedDialogs, []);
    assert.ok(
      submitted.revisions.reduce((n, revision) => n + revision.model_calls, 0) +
        finishedMemo.model_calls <=
        6,
    );
    receipt.reserved_model_calls =
      submitted.revisions.reduce((n, revision) => n + revision.model_calls, 0) +
      finishedMemo.model_calls;
    receipt.new_reserved_model_calls = receipt.reserved_model_calls - priorCalls;
    await page.screenshot({
      path: path.join(folder, `${engine}-completed.png`),
      fullPage: true,
    });
    stage("three_grounded_paragraphs_and_reload_verified");
    receipt.status = "passed";
  } catch (error) {
    receipt.status = "failed";
    receipt.errors.push({ name: error.name, message: error.message });
    process.exitCode = 1;
    if (page)
      try {
        await page.screenshot({
          path: path.join(folder, `${engine}-failure.png`),
          fullPage: true,
        });
      } catch {
        /* browser may already be closed */
      }
  } finally {
    clearInterval(timer);
    if (context) {
      try {
        await context.tracing.stop({ path: path.join(folder, "trace.zip") });
      } catch (error) {
        receipt.trace_error = error.name;
      }
      try {
        await context.close();
      } catch (error) {
        receipt.context_drain_error = error.name;
        receipt.status = "failed";
        process.exitCode = 1;
      }
    }
    if (browser)
      try {
        await browser.close();
      } catch (error) {
        receipt.browser_drain_error = error.name;
        receipt.status = "failed";
        process.exitCode = 1;
      }
    if (children.size) {
      receipt.child_drain_unconfirmed = true;
      receipt.status = "failed";
      process.exitCode = 1;
    }
    receipt.source_unchanged =
      JSON.stringify(sourceFiles()) === JSON.stringify(plan.ui_source_files);
    if (!receipt.source_unchanged) {
      receipt.status = "failed";
      process.exitCode = 1;
    }
    receipt.finished_utc = new Date().toISOString();
    save();
    if (slotOwned && slotPath && slot && fs.existsSync(slotPath)) {
      const current = read(slotPath);
      if (current.pid === process.pid && current.output_folder === folder) {
        slot.status = receipt.status;
        slot.finished_utc = receipt.finished_utc;
        slot.actual_reserved_calls = receipt.new_reserved_model_calls ?? null;
        slot.unknown_calls_remain_charged_at_upper_bound =
          slot.actual_reserved_calls === null;
        write(slotPath, slot);
      }
    }
    console.log(
      JSON.stringify({
        engine,
        status: receipt.status,
        reserved_model_calls: receipt.reserved_model_calls ?? null,
        scored_cohort_credit: false,
      }),
    );
  }
}
