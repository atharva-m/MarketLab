import { test, expect, type Page, type Route } from "@playwright/test";
const version = "a".repeat(64);
const run = "11111111-1111-4111-8111-111111111111";
const requestID = "22222222-2222-4222-8222-222222222222";
const spec = {
  schema: "research-spec-v1",
  workflow: "market_profile",
  symbols: ["BTCUSDT"],
  dataset_versions: [version],
  start: "2025-01-01T01:00:00Z",
  end: "2025-01-02T00:00:00Z",
  history_start: "2025-01-01T00:00:00Z",
  interval: "5m",
  metrics: ["profile"],
  parameters: {},
  predicates: {},
};
const json = (route: Route, data: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(data),
  });
async function mocks(page: Page) {
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/v1/datasets")
      return route.fulfill({
        contentType: "application/json",
        body: `{"items":[{"dataset_version_id":"${version}","symbol":"BTCUSDT","trade_date":"2025-01-01","row_count":9223372036854775807,"verification":"registered_metadata"}],"next_cursor":null}`,
      });
    if (path === `/v1/datasets/${version}`)
      return json(route, {
        dataset_version_id: version,
        verification: "verified",
        manifest: {
          source: { actual_sha256: "hash" },
          quality: { accepted_rows: 42 },
        },
      });
    if (path === `/v1/research/runs/${run}`)
      return json(route, {
        run_id: run,
        state: "succeeded",
        attempt_count: 1,
        spec,
        fingerprint: { source: "source-hash" },
      });
    if (path.endsWith("/summary"))
      return json(route, {
        schema: "research-summary-v1",
        profile: {
          vwap: {
            value: "12345.123456789012345678",
            reason: null,
            observation_count: 2,
          },
          correlation: {
            value: null,
            reason: "zero_variance",
            observation_count: 2,
          },
        },
      });
    if (path.endsWith("/results"))
      return json(route, {
        schema: "research-results-v1",
        profiles: { BTCUSDT: { trade_count: "9223372036854775807" } },
        clusters: [
          { start: "2025-01-01T01:00:00Z", end: "2025-01-01T01:10:00Z" },
        ],
      });
    if (path.endsWith("/memo"))
      return json(route, { detail: "Memo artifact integrity failure" }, 422);
    if (path === "/v1/research/runs")
      return json(route, { items: [], next_cursor: null });
    if (path === "/v1/copilot/requests")
      return json(route, { items: [], next_cursor: null });
    if (path === "/v1/ingestion/submissions")
      return json(route, { items: [], next_cursor: null });
    return json(route, { detail: "Not found" }, 404);
  });
}
const unexpectedErrors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }, testInfo) => {
  const errors: string[] = [];
  unexpectedErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    const expectedHTTP =
      /Failed to load resource.*status of (404|409|422|503)/.test(
        message.text(),
      );
    const expectedLost =
      testInfo.title.startsWith("lost response") &&
      /Failed to load resource/.test(message.text());
    if (message.type() === "error" && !expectedHTTP && !expectedLost)
      errors.push(message.text());
  });
  await mocks(page);
});
test.afterEach(async ({ page }) => {
  expect(unexpectedErrors.get(page) ?? [], "unexpected browser errors").toEqual(
    [],
  );
});
test("catalog requires explicit versions and preserves int64 row count", async ({
  page,
}) => {
  await page.goto("/#/catalog");
  await expect(
    page.getByText("9223372036854775807", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Research with 0 selected" }),
  ).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("link", { name: "Research with 1 selected" }).click();
  await expect(page.getByTestId("dataset-version-ids")).toHaveValue(version);
  await expect(
    page.getByRole("heading", { name: "New research run" }),
  ).toBeVisible();
});
test("research submits pinned spec once and retains responsive validation state", async ({
  page,
}) => {
  let posts = 0;
  let received: any;
  await page.route("**/v1/research/runs", async (route) => {
    if (route.request().method() === "POST") {
      posts++;
      received = route.request().postDataJSON();
      await new Promise((resolve) => setTimeout(resolve, 150));
      return json(route, { run_id: run, replayed: false }, 201);
    }
    return json(route, { items: [], next_cursor: null });
  });
  await page.goto("/#/research/new");
  await page.getByTestId("dataset-version-ids").fill(version);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("cross_asset");
  await page.getByTestId("submit-research").dblclick();
  await expect(
    page.getByText("Validation can take several minutes", { exact: false }),
  ).toBeVisible();
  await expect(page.getByTestId("run-id")).toHaveText(run);
  expect(posts).toBe(1);
  expect(received.symbols).toEqual(["BTCUSDT", "ETHUSDT"]);
  expect(received.dataset_versions).toEqual([version]);
  expect(received.history_start).toBe("2025-01-01T00:00:00Z");
});
test("lost response survives reload without automatic POST and retries exact key/body", async ({
  page,
}) => {
  const seen: { key: string | undefined; body: string | null }[] = [];
  await page.route("**/v1/research/runs", async (route) => {
    if (route.request().method() === "POST") {
      seen.push({
        key: route.request().headers()["idempotency-key"],
        body: route.request().postData(),
      });
      if (seen.length === 1) return route.abort("failed");
      return json(route, { run_id: run, replayed: true });
    }
    return json(route, { items: [], next_cursor: null });
  });
  await page.goto("/#/research/new");
  await page.getByTestId("dataset-version-ids").fill(version);
  await page.getByTestId("submit-research").click();
  await expect(
    page.getByRole("button", { name: "Retry saved operation" }),
  ).toBeEnabled();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Retry saved operation" }),
  ).toBeVisible();
  await page.waitForTimeout(250);
  expect(seen).toHaveLength(1);
  await page.getByRole("button", { name: "Retry saved operation" }).click();
  await expect(page.getByTestId("run-id")).toHaveText(run);
  expect(seen[0]).toEqual(seen[1]);
});
test("numerical exact values and null reasons remain visible through memo corruption", async ({
  page,
}) => {
  await page.goto(`/#/runs/${run}`);
  await expect(page.getByTestId("numerical-summary")).toContainText(
    "12345.123456789012345678",
  );
  await expect(page.getByTestId("numerical-summary")).toContainText(
    "zero_variance",
  );
  await expect(page.getByTestId("numerical-summary")).toContainText(
    "Unavailable (null)",
  );
  await expect(page.getByTestId("memo-panel")).toContainText(
    "Memo artifact integrity failure",
  );
  await expect(page.getByTestId("numerical-summary")).toBeVisible();
});
test("ready memo is three text paragraphs and cannot execute HTML", async ({
  page,
}) => {
  await page.route(`**/v1/research/runs/${run}/memo`, (route) =>
    json(route, {
      status: "ready",
      state: "ready",
      content:
        "Generated content: scope.\n\n<img src=x onerror=alert(1)> findings.\n\nDescriptive statistics are not predictions.",
      memo_sha256: "memo-hash",
    }),
  );
  await page.goto(`/#/runs/${run}`);
  const content = page.locator(".memo-content");
  await expect(content.locator("p")).toHaveCount(3);
  await expect(content).toContainText("<img src=x onerror=alert(1)>");
  await expect(content.locator("img")).toHaveCount(0);
});
test("chart is explicit and bounded, gaps stay empty, edits hide old plot", async ({
  page,
}) => {
  let reads = 0;
  await page.route("**/v1/bars?**", (route) => {
    reads++;
    return json(route, {
      symbol: "BTCUSDT",
      interval: "1m",
      start: "2025-01-01T01:00:00Z",
      end: "2025-01-01T01:03:00Z",
      expected_buckets: 3,
      returned_buckets: 2,
      empty_buckets: 1,
      bars: [
        {
          start: "2025-01-01T01:00:00Z",
          open: "10.000000000000000000",
          high: "11.000000000000000000",
          low: "9.000000000000000000",
          close: "10.500000000000000000",
          base_volume: "2.000000000000000000",
          quote_volume: "21.000000000000000000",
          trade_count: 2,
          vwap: "10.500000000000000000",
        },
        {
          start: "2025-01-01T01:02:00Z",
          open: "12.000000000000000000",
          high: "13.000000000000000000",
          low: "11.000000000000000000",
          close: "12.500000000000000000",
          base_volume: "1.000000000000000000",
          quote_volume: "12.500000000000000000",
          trade_count: 1,
          vwap: "12.500000000000000000",
        },
      ],
    });
  });
  await page.goto(`/#/runs/${run}`);
  await expect(
    page.getByRole("heading", { name: "Price and base volume" }),
  ).toBeVisible();
  expect(reads).toBe(0);
  await page.getByLabel("Chart interval").selectOption("1m");
  await page
    .getByLabel("Chart end (UTC, exclusive)")
    .fill("2025-01-01T01:03:00Z");
  await page.getByLabel("Chart dataset version IDs").fill(version);
  await page.getByRole("button", { name: "Load chart window" }).click();
  await expect(page.getByRole("img")).toBeVisible();
  await expect(
    page.getByText("2 of 3 buckets observed, 1 empty"),
  ).toBeVisible();
  expect(reads).toBe(1);
  await expect(page.locator("svg g")).toHaveCount(2);
  await page.getByLabel("Chart start (UTC)").fill("2025-01-01T01:01:00Z");
  await expect(page.getByRole("img")).toHaveCount(0);
  expect(reads).toBe(1);
  await page.getByLabel("Chart start (UTC)").fill("incomplete");
  await page.getByRole("button", { name: "Next window" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "valid aligned January UTC" }),
  ).toContainText("valid aligned January UTC");
});
test("copilot stale answer refreshes revision and preserves safe state", async ({
  page,
}) => {
  let revision = 1;
  await page.route(`**/v1/copilot/requests/${requestID}`, (route) =>
    json(route, {
      request_id: requestID,
      current_revision: revision,
      state: "completed",
      outcome: "needs_clarification",
      body: { text: "Show volume" },
      revisions: [
        {
          revision,
          state: "completed",
          outcome: "needs_clarification",
          questions: ["Specify evaluation period and metric."],
          attempt_count: 1,
          model_calls: 1,
        },
      ],
    }),
  );
  await page.route(
    `**/v1/copilot/requests/${requestID}/clarifications`,
    (route) => {
      expect(route.request().postDataJSON().expected_revision).toBe(1);
      revision = 2;
      return json(route, { detail: "Copilot revision conflict" }, 409);
    },
  );
  await page.goto(`/#/copilot/${requestID}`);
  await page.getByLabel("Clarification answer").fill("Use VWAP.");
  await page.getByRole("button", { name: "Submit clarification" }).click();
  await expect(
    page.getByText("Revision 2 of at most 5 clarification rounds"),
  ).toBeVisible();
  await expect(page.getByText("Copilot revision conflict")).toHaveCount(0);
});
test("keyboard skip preserves route and responsive navigation stays usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/research/new");
  await expect(
    page.getByRole("heading", { name: "New research run" }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Skip to content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
  expect(page.url()).toContain("#/research/new");
  await expect(
    page.getByRole("heading", { name: "New research run" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("new local mutation proxy rejects foreign browser origin", async ({
  request,
}) => {
  const response = await request.post("/v1/research/runs", {
    headers: {
      Origin: "https://foreign.example",
      "Content-Type": "application/json",
    },
    data: {},
  });
  expect(response.status()).toBe(403);
});
test("ingestion submission and job discovery show partial daily outcomes", async ({
  page,
}) => {
  const submission = "33333333-3333-4333-8333-333333333333";
  await page.route("**/v1/ingestion/submissions", (route) => {
    if (route.request().method() === "POST") {
      expect(route.request().postDataJSON()).toEqual({
        schema: "ingestion-submission-v1",
        symbols: ["BTCUSDT", "ETHUSDT"],
        start_date: "2025-01-31",
        before_date: "2025-02-01",
      });
      return json(route, { submission_id: submission }, 201);
    }
    return json(route, { items: [], next_cursor: null });
  });
  await page.route("**/v1/ingestion/submissions?**", (route) =>
    json(route, {
      items: [
        {
          submission_id: submission,
          created_at: "2026-10-26T12:00:00Z",
          succeeded: 1,
          total: 2,
        },
      ],
      next_cursor: null,
    }),
  );
  await page.route(`**/v1/ingestion/submissions/${submission}`, (route) =>
    json(route, {
      submission: { submission_id: submission },
      total: 2,
      succeeded: 1,
      failed: 1,
      complete: false,
      jobs: [
        {
          job_id: "one",
          symbol: "BTCUSDT",
          trade_date: "2025-01-31",
          state: "succeeded",
          attempt_count: 1,
          result_version: version,
          attempts: [{ attempt_number: 1, outcome: "succeeded" }],
        },
        {
          job_id: "two",
          symbol: "ETHUSDT",
          trade_date: "2025-01-31",
          state: "failed",
          attempt_count: 3,
          error: "Source integrity failure",
          attempts: [{ attempt_number: 3, outcome: "permanent" }],
        },
      ],
    }),
  );
  await page.goto("/#/ingestion/new");
  await page.getByLabel("ETHUSDT", { exact: true }).check();
  await page.getByLabel("First UTC date (inclusive)").fill("2025-01-31");
  await page.getByLabel("Before UTC date (exclusive)").fill("2025-02-01");
  await page
    .getByRole("button", { name: "Submit ingestion", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Ingestion submission" }),
  ).toBeVisible();
  await expect(
    page.getByText("Partial / pending", { exact: true }),
  ).toBeVisible();
  await page.getByText("ETHUSDT · 2025-01-31", { exact: false }).click();
  await expect(
    page.getByText("Source integrity failure", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await page.getByLabel("Job family").selectOption("ingestion");
  await page.getByRole("link").filter({ hasText: submission }).click();
  await expect(
    page.getByRole("heading", { name: "Ingestion submission" }),
  ).toBeVisible();
});
test("unsupported copilot creation stays terminal without research execution link", async ({
  page,
}) => {
  await page.route("**/v1/copilot/requests", (route) => {
    expect(route.request().postDataJSON().context).toEqual({});
    expect(route.request().postDataJSON().dataset_versions).toEqual([version]);
    return json(
      route,
      { request_id: requestID, revision: 0, replayed: false },
      201,
    );
  });
  await page.route(`**/v1/copilot/requests/${requestID}`, (route) =>
    json(route, {
      request_id: requestID,
      current_revision: 0,
      state: "completed",
      outcome: "unsupported",
      body: { text: "Predict next month Bitcoin price" },
      revisions: [
        {
          revision: 0,
          state: "completed",
          outcome: "unsupported",
          attempt_count: 1,
          model_calls: 1,
        },
      ],
    }),
  );
  await page.goto("/#/copilot/new");
  await page
    .getByLabel("Research request")
    .fill("Predict next month Bitcoin price");
  await page.getByTestId("dataset-version-ids").fill(version);
  await page.getByRole("button", { name: "Submit copilot request" }).click();
  await expect(
    page.getByRole("heading", { name: "Copilot request", exact: true }),
  ).toBeVisible();
  await expect(page.locator("header .tag")).toHaveText("unsupported");
  await expect(
    page.getByRole("link", { name: "Open research run" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Submit clarification" }),
  ).toHaveCount(0);
});
