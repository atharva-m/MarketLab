import { test, expect, type Page, type Route } from "@playwright/test";
import { createHash } from "node:crypto";

// Mocked browser interaction coverage supplements the separately owned actual
// API/worker acceptance campaign; it is never reported as actual ingestion.
const version = "d".repeat(64);
const run = "44444444-4444-4444-8444-444444444444";
const imported = "55555555-5555-4555-8555-555555555555";
const generation = "66666666-6666-4666-8666-666666666666";
const instrument = {
  instrument_id: "binance:spot:SOLUSDT",
  display_name: "SOL <script>alert(1)</script>",
  source_symbol: "SOLUSDT",
  base_asset: "SOL",
  quote_asset: "USDT",
  enabled: true,
  revision: 0,
};
const dataset = {
  dataset_version_id: version,
  instrument_id: instrument.instrument_id,
  trade_date: "2025-03-01",
  row_count: "9223372036854775807",
  contract: "dataset-manifest-v2",
};
const json = (route: Route, data: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(data),
  });
async function mocks(page: Page, empty = false) {
  await page.route("**/v1/**", (route) =>
    json(route, { items: [], next_cursor: null }),
  );
  await page.route("**/v2/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/v2/")) return route.fallback();
    if (path === "/v2/capabilities")
      return json(route, {
        auth_mode: "local",
        storage_mode: "local",
        limits: {
          partitions: 62,
          research_buckets: 17856,
          chart_buckets: 1440,
        },
      });
    if (path === "/v2/instruments")
      return json(route, {
        items: empty ? [] : [instrument],
        next_cursor: null,
      });
    if (path.startsWith("/v2/instruments/")) return json(route, instrument);
    if (path === "/v2/datasets")
      return json(route, { items: empty ? [] : [dataset], next_cursor: null });
    if (path === "/v2/coverage")
      return json(route, {
        instrument_id: instrument.instrument_id,
        coverage_claim: "observed_only",
        gaps: [],
        days: [
          {
            date: "2025-03-01",
            versions: [dataset],
            next_cursor: null,
            observed_bounds_complete: true,
            observed_start: "2025-03-01T00:00:00Z",
            observed_end: "2025-03-01T23:59:59Z",
          },
        ],
      });
    return json(
      route,
      {
        error: {
          code: "not_found",
          message: "Unmocked resource",
          request_id: "test",
        },
      },
      404,
    );
  });
}

test("empty catalog shows onboarding and does not invent default instruments or dates", async ({
  page,
}) => {
  await mocks(page, true);
  await page.goto("/#/v2/catalog");
  await expect(
    page.getByRole("heading", { name: "No registered data in this view" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Import a canonical file", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("From UTC date (inclusive)")).toHaveValue("");
  await expect(page.getByLabel("Instrument", { exact: true })).toHaveValue("");
});

test("catalog preserves exact counts, escapes metadata, pins March data and restores selection", async ({
  page,
}) => {
  await mocks(page);
  await page.goto("/#/v2/catalog");
  await expect(
    page.getByText("9223372036854775807", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Instrument", { exact: true })).toHaveValue(
    instrument.instrument_id,
  );
  await expect(
    page.locator("script").filter({ hasText: "alert(1)" }),
  ).toHaveCount(0);
  await page
    .getByRole("checkbox", { name: /Pin binance:spot:SOLUSDT/ })
    .check();
  await page.getByRole("link", { name: "Research this selection" }).click();
  await expect(
    page.getByRole("heading", { name: "Explicit pinned versions · 1/62" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Explicit pinned versions · 1/62" }),
  ).toBeVisible();
  await expect(page.getByLabel("History start UTC (inclusive)")).toHaveValue(
    "",
  );
});

test("coverage suggestions require confirmation and submit only exact pinned numerical spec", async ({
  page,
}) => {
  await mocks(page);
  let submitted: any;
  await page.route("**/v2/research/runs", (route) => {
    submitted = route.request().postDataJSON();
    return json(route, { id: run, state: "queued" }, 201);
  });
  await page.route(`**/v2/research/runs/${run}`, (route) =>
    json(route, {
      state: "queued",
      attempt_count: 0,
      revision: 0,
      numerical_available: false,
      spec: submitted,
      fingerprint: {
        instruments: { [instrument.instrument_id]: instrument },
        datasets: [dataset],
      },
      attempts: [],
    }),
  );
  await page.goto("/#/v2/research/new");
  await expect(
    page.getByRole("checkbox", { name: /SOL <script>/ }),
  ).toBeChecked();
  await page
    .getByLabel("Coverage from UTC date", { exact: true })
    .fill("2025-03-01");
  await page
    .getByLabel("Coverage before UTC date (exclusive)")
    .fill("2025-03-02");
  await page.getByRole("button", { name: "Load registered coverage" }).click();
  await page
    .getByRole("button", { name: "Use latest unambiguous registered interval" })
    .click();
  await expect(page.getByLabel("Evaluation start UTC (inclusive)")).toHaveValue(
    "2025-03-01T01:00:00Z",
  );
  await page
    .getByRole("button", { name: "Submit pinned numerical research" })
    .click();
  await expect(page.getByRole("alert")).toContainText("Confirm");
  expect(submitted).toBeUndefined();
  await page
    .getByRole("checkbox", { name: /I confirm these exact versions/ })
    .check();
  await page
    .getByRole("button", { name: "Submit pinned numerical research" })
    .click();
  await expect(page).toHaveURL(new RegExp(`/v2/runs/${run}`));
  expect(submitted).toEqual({
    schema: "research-spec-v2",
    workflow: "market_profile",
    instrument_ids: [instrument.instrument_id],
    dataset_versions: [version],
    history_start: "2025-03-01T00:00:00Z",
    start: "2025-03-01T01:00:00Z",
    end: "2025-03-02T00:00:00Z",
    interval: "5m",
    metrics: ["profile"],
    parameters: {},
    predicates: {},
  });
});

test("real browser worker hashes a File and upload status avoids persistent capabilities", async ({
  page,
}, testInfo) => {
  await mocks(page);
  const content = Buffer.from(
    "source_trade_id,executed_at,price,quantity,quote_quantity,is_buyer_maker,is_best_match\n1,2025-03-01T00:00:00Z,1,2,2,true,true\n",
  );
  const expected = createHash("sha256").update(content).digest("hex");
  let state = "awaiting_upload";
  let body: any;
  let puts = 0;
  await page.route("**/v2/imports", (route) => {
    body = route.request().postDataJSON();
    return json(
      route,
      {
        id: imported,
        state,
        revision: 0,
        upload: {
          method: "PUT",
          url: `/v2/imports/${imported}/content`,
          generation,
          expires_at: "2099-01-01T00:00:00Z",
          required_headers: {
            "Content-Type": "application/octet-stream",
            "X-Upload-Token": "private-one-use-token",
          },
        },
      },
      201,
    );
  });
  await page.route(`**/v2/imports/${imported}`, (route) =>
    json(route, {
      id: imported,
      state,
      revision: state === "uploaded" ? 2 : 0,
      declared_bytes: content.length,
      received_bytes: state === "uploaded" ? content.length : 0,
      source_sha256: expected,
      generation,
      generation_expires_at: "2099-01-01T00:00:00Z",
      error: null,
    }),
  );
  await page.route(`**/v2/imports/${imported}/content`, async (route) => {
    puts++;
    const observed = route.request().postDataBuffer();
    if (observed) expect(observed.equals(content)).toBe(true);
    else {
      // WebKit's Playwright File-body interceptor omits bytes. The separate
      // actual API campaign must verify raw wire length/hash for every engine.
      expect(testInfo.project.name).toBe("webkit");
      testInfo.annotations.push({
        type: "observer-limit",
        description:
          "WebKit File bytes unavailable to Playwright interception; actual API hash/length gate required.",
      });
    }
    expect((await route.request().allHeaders())["x-upload-token"]).toBe(
      "private-one-use-token",
    );
    state = "uploaded";
    return json(route, { id: imported, state, revision: 2 });
  });
  await page.goto("/#/v2/imports/new");
  await expect(page.getByLabel("Instrument", { exact: true })).toHaveValue(
    instrument.instrument_id,
  );
  await page.getByLabel("Trade UTC date").fill("2025-03-01");
  await page
    .getByLabel("Source name", { exact: true })
    .fill("verified-binance-conversion");
  await page
    .getByRole("checkbox", { name: /I confirm this is Binance-origin/ })
    .check();
  await page.getByLabel("Canonical daily file", { exact: true }).setInputFiles({
    name: "source.csv",
    mimeType: "text/csv",
    buffer: content,
  });
  await page
    .getByRole("button", { name: "Hash and upload canonical file" })
    .click();
  await expect(
    page.getByRole("button", { name: "Finalize verified import" }),
  ).toBeVisible();
  expect(body.manifest.source_sha256).toBe(expected);
  expect(body.content_length).toBe(content.length);
  const storage = await page.evaluate(() =>
    JSON.stringify({ ...localStorage, ...sessionStorage }),
  );
  expect(storage).not.toContain("private-one-use-token");
  await page.getByRole("link", { name: "Catalog", exact: true }).click();
  await page.getByRole("link", { name: "File import", exact: true }).click();
  await expect(page.getByLabel("Instrument", { exact: true })).toHaveValue(
    instrument.instrument_id,
  );
  await page.getByLabel("Trade UTC date").fill("2025-03-01");
  await page
    .getByLabel("Source name", { exact: true })
    .fill("verified-binance-conversion");
  await page
    .getByRole("checkbox", { name: /I confirm this is Binance-origin/ })
    .check();
  await page
    .getByLabel("Canonical daily file", { exact: true })
    .setInputFiles({
      name: "source.csv",
      mimeType: "text/csv",
      buffer: content,
    });
  await page
    .getByRole("button", { name: "Hash and upload canonical file" })
    .click();
  await expect(
    page.getByRole("button", { name: "Finalize verified import" }),
  ).toBeVisible();
  expect(puts).toBe(1);
  await expect(page.getByRole("status")).toContainText(
    "No file bytes were retried automatically",
  );
  await page.reload();
  await expect(
    page.getByLabel("Canonical daily file", { exact: true }),
  ).toHaveValue("");
});

test("a sole last-page instrument never becomes a unique-catalog default", async ({
  page,
}) => {
  await mocks(page);
  await page.route("**/v2/instruments?**", (route) => {
    const last = new URL(route.request().url()).searchParams.has("cursor");
    return json(
      route,
      last
        ? { items: [instrument], next_cursor: null }
        : {
            items: Array.from({ length: 100 }, (_, i) => ({
              ...instrument,
              instrument_id: `binance:spot:SYMBOL${i}`,
              source_symbol: `SYMBOL${i}`,
              display_name: `Symbol ${i}`,
            })),
            next_cursor: "last-page",
          },
    );
  });
  await page.goto("/#/v2/catalog");
  await expect(page.getByLabel("Instrument", { exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "Next instrument page" }).click();
  await expect(
    page.getByRole("button", { name: "First instrument page" }),
  ).toBeVisible();
  await expect(page.getByLabel("Instrument", { exact: true })).toHaveValue("");
  await page
    .getByRole("link", { name: "Official ingestion", exact: true })
    .click();
  await page.getByRole("button", { name: "Next instrument page" }).click();
  await expect(
    page.getByRole("checkbox", { name: /SOL <script>/ }),
  ).not.toBeChecked();
});

test("official success exposes the actual result_version without changing the job response shape", async ({
  page,
}) => {
  await mocks(page);
  await page.route(`**/v2/ingestion/submissions/${imported}`, (route) =>
    json(route, {
      submission: { submission_id: imported },
      jobs: [
        {
          job_id: generation,
          instrument_id: instrument.instrument_id,
          trade_date: "2025-03-01",
          state: "succeeded",
          revision: 3,
          attempt_count: 1,
          result_version: version,
          attempts: [],
        },
      ],
    }),
  );
  await page.goto(`/#/v2/submissions/${imported}`);
  await expect(
    page.getByText("Published version:", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open catalog and pin this version" }),
  ).toBeVisible();
  await expect(page.locator('code[title="' + version + '"]')).toBeVisible();
});

test("replayed creation reads current durable status and never automatically replays file bytes", async ({
  page,
}) => {
  await mocks(page);
  const content = Buffer.from("retained bytes");
  const hash = createHash("sha256").update(content).digest("hex");
  let puts = 0;
  await page.route("**/v2/imports", (route) =>
    json(route, {
      id: imported,
      state: "awaiting_upload",
      revision: 0,
      replayed: true,
      upload: {
        method: "PUT",
        url: `/v2/imports/${imported}/content`,
        generation,
        expires_at: "2099-01-01T00:00:00Z",
        required_headers: {
          "Content-Type": "application/octet-stream",
          "X-Upload-Token": "private-replay-token",
        },
      },
    }),
  );
  await page.route(`**/v2/imports/${imported}`, (route) =>
    json(route, {
      id: imported,
      state: "uploaded",
      revision: 2,
      declared_bytes: content.length,
      received_bytes: content.length,
      source_sha256: hash,
      generation,
      error: null,
    }),
  );
  await page.route(`**/v2/imports/${imported}/content`, (route) => {
    puts++;
    return json(
      route,
      { error: { code: "revision_conflict", message: "Already claimed" } },
      409,
    );
  });
  await page.goto("/#/v2/imports/new");
  await expect(page.getByLabel("Instrument", { exact: true })).toHaveValue(
    instrument.instrument_id,
  );
  await page.getByLabel("Trade UTC date").fill("2025-03-01");
  await page
    .getByLabel("Source name", { exact: true })
    .fill("binance-retained");
  await page
    .getByRole("checkbox", { name: /I confirm this is Binance-origin/ })
    .check();
  await page.getByLabel("Canonical daily file", { exact: true }).setInputFiles({
    name: "source.csv",
    mimeType: "text/csv",
    buffer: content,
  });
  await page
    .getByRole("button", { name: "Hash and upload canonical file" })
    .click();
  await expect(
    page.getByRole("button", { name: "Finalize verified import" }),
  ).toBeVisible();
  expect(puts).toBe(0);
  await expect(page.getByRole("status")).toContainText(
    "No file bytes were retried automatically",
  );
});

test("changing coverage dates discards a pending response and cannot restore stale suggested pins", async ({
  page,
}) => {
  await mocks(page);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started: (() => void) | undefined;
  const requested = new Promise<void>((resolve) => {
    started = resolve;
  });
  await page.route("**/v2/coverage?**", async (route) => {
    started?.();
    await held;
    try {
      await json(route, {
        instrument_id: instrument.instrument_id,
        coverage_claim: "observed_only",
        gaps: [],
        days: [
          {
            date: "2025-03-01",
            versions: [dataset],
            next_cursor: null,
            observed_bounds_complete: true,
          },
        ],
      });
    } catch {
      /* browser correctly aborted stale request */
    }
  });
  await page.goto("/#/v2/research/new");
  await expect(
    page.getByRole("checkbox", { name: /SOL <script>/ }),
  ).toBeChecked();
  await page
    .getByLabel("Coverage from UTC date", { exact: true })
    .fill("2025-03-01");
  await page
    .getByLabel("Coverage before UTC date (exclusive)")
    .fill("2025-03-02");
  await page.getByRole("button", { name: "Load registered coverage" }).click();
  await requested;
  await page
    .getByLabel("Coverage from UTC date", { exact: true })
    .fill("2025-03-02");
  release?.();
  await expect(
    page.getByRole("button", { name: "Load registered coverage" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", {
      name: "Use latest unambiguous registered interval",
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Explicit pinned versions · 0/62" }),
  ).toBeVisible();
});
