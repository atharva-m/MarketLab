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
  let accept!: () => void;
  const pending = new Promise<void>((resolve) => {
    accept = resolve;
  });
  await page.route("**/v1/research/runs", async (route) => {
    if (route.request().method() === "POST") {
      posts++;
      received = route.request().postDataJSON();
      await pending;
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
  await expect(page.getByTestId("submit-research")).toBeDisabled();
  await expect(
    page.getByText("The last request has no confirmed outcome"),
  ).toHaveCount(0);
  expect(posts).toBe(1);
  accept();
  await expect(page.getByTestId("run-id")).toHaveText(run);
  expect(posts).toBe(1);
  expect(received.symbols).toEqual(["BTCUSDT", "ETHUSDT"]);
  expect(received.dataset_versions).toEqual([version]);
  expect(received.history_start).toBe("2025-01-01T00:00:00Z");
});

test("matrix click, shift range, drag and table share exact persisted versions", async ({
  page,
}) => {
  const ids = ["a", "b", "c"].map((c) => c.repeat(64));
  await page.route("**/v1/datasets?**", (route) =>
    json(route, {
      items: ids.map((id, i) => ({
        dataset_version_id: id,
        symbol: "BTCUSDT",
        trade_date: `2025-01-0${i + 1}`,
        row_count: String(i + 1),
      })),
      next_cursor: null,
    }),
  );
  await page.goto("/#/catalog");
  const cells = page.locator(".matrix button");
  await expect(cells).toHaveCount(3);
  await cells.nth(0).click();
  await cells.nth(2).click({ modifiers: ["Shift"] });
  await expect(page.getByRole("checkbox", { checked: true })).toHaveCount(3);
  await expect(
    page.getByRole("link", { name: "Research with 3 selected" }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByRole("checkbox", { checked: true })).toHaveCount(3);
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  const start = await cells.nth(0).boundingBox();
  const end = await cells.nth(2).boundingBox();
  await page.mouse.move(
    start!.x + start!.width / 2,
    start!.y + start!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(end!.x + end!.width / 2, end!.y + end!.height / 2, {
    steps: 20,
  });
  await page.mouse.up();
  await expect(page.getByRole("checkbox", { checked: true })).toHaveCount(3);
  await page.getByRole("link", { name: "Research with 3 selected" }).click();
  await expect(page.getByTestId("dataset-version-ids")).toHaveValue(
    ids.join("\n"),
  );
});

test("matrix with multiple versions requires explicit table choice", async ({
  page,
}) => {
  const ids = ["a", "b"].map((c) => c.repeat(64));
  await page.route("**/v1/datasets?**", (route) =>
    json(route, {
      items: ids.map((id) => ({
        dataset_version_id: id,
        symbol: "BTCUSDT",
        trade_date: "2025-01-01",
        row_count: "10",
      })),
      next_cursor: null,
    }),
  );
  await page.goto("/#/catalog");
  await page.getByRole("button", { name: /trades, 2 versions/ }).click();
  await expect(page.getByRole("checkbox", { checked: true })).toHaveCount(0);
  await expect(page.getByLabel("Asset", { exact: true })).toHaveValue(
    "BTCUSDT",
  );
  await page.getByRole("checkbox").nth(1).check();
  await page.getByRole("link", { name: "Research with 1 selected" }).click();
  await expect(page.getByTestId("dataset-version-ids")).toHaveValue(ids[1]);
});

test("command menu supports keyboard selection, ID navigation, focus restore and empty search", async ({
  page,
}) => {
  await page.goto("/#/catalog");
  const jump = page.getByRole("button", { name: "Jump to…" });
  await jump.click();
  const input = page.getByRole("combobox", { name: "Search commands" });
  await expect(input).toBeFocused();
  await input.fill("nothing-matches");
  await expect(page.getByText("No matches", { exact: true })).toBeVisible();
  await input.press("Enter");
  await expect(
    page.getByRole("dialog", { name: "Command menu" }),
  ).toBeVisible();
  await input.press("Escape");
  await expect(jump).toBeFocused();
  await page.keyboard.press("Control+k");
  await input.fill(run.toUpperCase());
  await expect(page.getByRole("dialog").getByRole("option")).toHaveCount(3);
  await input.press("Enter");
  await expect(page.getByTestId("run-id")).toHaveText(run);
  await page.keyboard.press("Control+k");
  await input.fill(version);
  await input.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Dataset verification" }),
  ).toBeVisible();
  await page.keyboard.press("Control+k");
  await input.fill("new research");
  await input.press("ArrowDown");
  await input.press("Enter");
  await expect(
    page.getByRole("heading", { name: "New research run" }),
  ).toBeVisible();
  await page.getByTestId("dataset-version-ids").fill("n");
  await page.keyboard.press("Control+k");
  await input.press("Escape");
  await expect(page.getByTestId("dataset-version-ids")).toBeFocused();
  await page.keyboard.press("g");
  await page.keyboard.press("d");
  expect(page.url()).toContain("#/research/new");
});

test("catalog continuation exposes versions and assets beyond the first thousand", async ({
  page,
}) => {
  let reads = 0;
  await page.route("**/v1/datasets?**", (route) => {
    reads++;
    const offset = Number(
      new URL(route.request().url()).searchParams.get("cursor") ?? 0,
    );
    const items = Array.from({ length: offset < 1000 ? 100 : 1 }, (_, i) => ({
      dataset_version_id: (offset + i + 1).toString(16).padStart(64, "0"),
      symbol: offset < 1000 ? "BTCUSDT" : "ETHUSDT",
      trade_date: "2025-01-01",
      row_count: "1",
    }));
    return json(route, {
      items,
      next_cursor: offset < 1000 ? String(offset + 100) : null,
    });
  });
  await page.goto("/#/catalog");
  const more = page.getByRole("button", {
    name: "Load more versions",
    exact: true,
  });
  await expect(more).toBeEnabled();
  const initialReads = reads;
  expect(initialReads).toBeGreaterThanOrEqual(10);
  expect(initialReads).toBeLessThanOrEqual(11); // StrictMode may abort the first page once.
  await more.click();
  await expect(more).toHaveCount(0);
  expect(reads).toBe(initialReads + 1);
  await page.getByLabel("Asset", { exact: true }).selectOption("ETHUSDT");
  await expect(page.getByRole("checkbox")).toHaveCount(1);
  await page.getByRole("checkbox").check();
  await page.getByRole("link", { name: "Research with 1 selected" }).click();
  await expect(page.getByTestId("dataset-version-ids")).toHaveValue(
    (1001).toString(16).padStart(64, "0"),
  );
});

test("run retries metadata errors and requires complete pinned metadata before close reads", async ({
  page,
}) => {
  const pinned = "f".repeat(64);
  let fail = true;
  let barReads = 0;
  await page.route(`**/v1/research/runs/${run}`, (route) =>
    json(route, {
      run_id: run,
      state: "succeeded",
      spec: { ...spec, dataset_versions: [pinned] },
    }),
  );
  await page.route("**/v1/datasets?**", (route) => {
    if (fail) return json(route, { detail: "Metadata unavailable" }, 422);
    const offset = Number(
      new URL(route.request().url()).searchParams.get("cursor") ?? 0,
    );
    return json(route, {
      items: Array.from({ length: offset < 1000 ? 100 : 1 }, (_, i) => ({
        dataset_version_id:
          offset < 1000
            ? (offset + i + 1).toString(16).padStart(64, "0")
            : pinned,
        symbol: "BTCUSDT",
        trade_date: "2025-01-01",
        row_count: "1",
      })),
      next_cursor: offset < 1000 ? String(offset + 100) : null,
    });
  });
  await page.route("**/v1/bars?**", (route) => {
    barReads++;
    return json(route, {
      bars: [],
      returned_buckets: 0,
      expected_buckets: 276,
    });
  });
  await page.goto(`/#/runs/${run}`);
  await expect(
    page.getByRole("alert").filter({ hasText: "Metadata unavailable" }),
  ).toBeVisible();
  fail = false;
  await page
    .getByRole("button", { name: "Retry pinned version lookup" })
    .click();
  await expect(
    page.getByRole("button", { name: "Load more pinned version metadata" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Load close price" }),
  ).toBeDisabled();
  expect(barReads).toBe(0);
  await page
    .getByRole("button", { name: "Load more pinned version metadata" })
    .click();
  await expect(
    page.getByRole("button", { name: "Load close price" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Load close price" }).click();
  await expect(page.locator("section.graphite").getByRole("img")).toBeVisible();
  expect(barReads).toBe(1);
});

test("queued run only describes and copies a scoped worker command", async ({
  page,
}) => {
  let posts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST") posts++;
  });
  await page.route(`**/v1/research/runs/${run}`, (route) =>
    json(route, { run_id: run, state: "queued", spec }),
  );
  await page.goto(`/#/runs/${run}`);
  await expect(
    page.getByRole("heading", { name: "Waiting for a research worker" }),
  ).toBeVisible();
  await expect(page.locator(".worker code")).toContainText(
    `python -m marketlab.research_cli worker --max-runs 1 --run ${run}`,
  );
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          (window as any).copied = value;
        },
      },
    });
  });
  await page.getByRole("button", { name: "Copy command" }).click();
  expect(await page.evaluate(() => (window as any).copied)).toBe(
    `python -m marketlab.research_cli worker --max-runs 1 --run ${run}`,
  );
  expect(posts).toBe(0);
});

test("close chart loads only on request and pages bounded pinned windows without bridging gaps", async ({
  page,
}) => {
  const ids = Array.from({ length: 7 }, (_, i) =>
    (i + 1).toString(16).repeat(64),
  );
  const reads: URL[] = [];
  await page.route(`**/v1/research/runs/${run}`, (route) =>
    json(route, {
      run_id: run,
      state: "succeeded",
      spec: { ...spec, end: "2025-01-08T00:00:00Z", dataset_versions: ids },
    }),
  );
  await page.route("**/v1/datasets?**", (route) =>
    json(route, {
      items: ids.map((id, i) => ({
        dataset_version_id: id,
        symbol: "BTCUSDT",
        trade_date: `2025-01-0${i + 1}`,
        row_count: "100",
      })),
      next_cursor: null,
    }),
  );
  await page.route("**/v1/bars?**", (route) => {
    const url = new URL(route.request().url());
    reads.push(url);
    const start = url.searchParams.get("start")!;
    const end = url.searchParams.get("end")!;
    return json(route, {
      start,
      end,
      returned_buckets: 2,
      expected_buckets: (Date.parse(end) - Date.parse(start)) / 300000,
      bars: [
        { start, close: "10.000000000000000001" },
        {
          start: new Date(Date.parse(start) + 600000).toISOString(),
          close: "11.000000000000000001",
        },
      ],
    });
  });
  await page.goto(`/#/runs/${run}`);
  const chart = page.locator("section.graphite");
  await expect(
    chart.getByRole("button", { name: "Load close price" }),
  ).toBeEnabled();
  expect(reads).toHaveLength(0);
  await chart.getByRole("button", { name: "Load close price" }).click();
  await expect(chart.getByRole("img")).toBeVisible();
  expect(reads).toHaveLength(1);
  expect(reads[0].searchParams.getAll("version")).toEqual(ids.slice(0, 5));
  expect(reads[0].searchParams.get("end")).toBe("2025-01-06T00:00:00Z");
  expect(await chart.locator("path.draw").getAttribute("d")).toMatch(
    /^M[^LM]+M/,
  );
  await chart.getByRole("button", { name: "Next 5 days" }).click();
  await expect(chart.getByRole("img")).toHaveAttribute("aria-label", /6 Jan/);
  expect(reads).toHaveLength(2);
  expect(reads[1].searchParams.getAll("version")).toEqual(ids.slice(5));
  expect(reads[1].searchParams.get("start")).toBe("2025-01-06T00:00:00Z");
  await expect(
    chart.getByRole("button", { name: "Next 5 days" }),
  ).toBeDisabled();
});

test("cross-asset closes read sequential pinned assets and preserve exact profile values", async ({
  page,
}) => {
  const ethVersion = "b".repeat(64);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  const symbols: string[] = [];
  await page.route(`**/v1/research/runs/${run}`, (route) =>
    json(route, {
      run_id: run,
      state: "succeeded",
      spec: {
        ...spec,
        workflow: "cross_asset",
        symbols: ["BTCUSDT", "ETHUSDT"],
        dataset_versions: [version, ethVersion],
      },
    }),
  );
  await page.route("**/v1/datasets?**", (route) =>
    json(route, {
      items: [version, ethVersion].map((id, i) => ({
        dataset_version_id: id,
        symbol: ["BTCUSDT", "ETHUSDT"][i],
        trade_date: "2025-01-01",
        row_count: "1",
      })),
      next_cursor: null,
    }),
  );
  await page.route(`**/v1/research/runs/${run}/summary`, (route) =>
    json(route, {
      profiles: {
        BTCUSDT: {
          vwap: { value: "12345.123456789012345678", observation_count: 2 },
          trade_count: "9223372036854775807",
        },
        ETHUSDT: {
          vwap: { value: "2345.123456789012345678", observation_count: 2 },
          trade_count: "9223372036854775806",
        },
      },
    }),
  );
  await page.route("**/v1/bars?**", async (route) => {
    const q = new URL(route.request().url()).searchParams;
    const symbol = q.get("symbol")!;
    symbols.push(symbol);
    expect(q.getAll("version")).toEqual([
      symbol === "BTCUSDT" ? version : ethVersion,
    ]);
    if (symbol === "BTCUSDT") await pending;
    return json(route, {
      returned_buckets: 2,
      expected_buckets: 276,
      bars: [
        { start: spec.start, close: "10.000000000000000001" },
        { start: "2025-01-01T01:05:00Z", close: "11.000000000000000001" },
      ],
    });
  });
  await page.goto(`/#/runs/${run}`);
  const numerical = page.getByTestId("numerical-summary");
  await expect(numerical).toContainText("12345.123456789012345678");
  await expect(numerical).toContainText("2345.123456789012345678");
  await expect(numerical).toContainText("9223372036854775806");
  expect(symbols).toEqual([]);
  await page.getByRole("button", { name: "Load closes" }).click();
  await expect.poll(() => symbols).toEqual(["BTCUSDT"]);
  release();
  const chart = page.locator("section.graphite");
  await expect(chart.getByRole("img")).toBeVisible();
  expect(symbols).toEqual(["BTCUSDT", "ETHUSDT"]);
  await expect(chart.locator("path.draw")).toHaveCount(2);
  for (const path of await chart.locator("path.draw").all())
    expect(await path.getAttribute("d")).not.toMatch(/NaN|Infinity/);
});

for (const width of [1440, 768, 390]) {
  test(`redesigned catalog and run fit ${width}px without document overflow`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ["/catalog", `/runs/${run}`]) {
      await page.goto(`/#${route}`);
      await expect(page.locator("main h1")).toBeVisible();
      if (route === "/catalog")
        await expect(page.locator(".matrix button")).toBeVisible();
      else await expect(page.getByTestId("numerical-summary")).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
      await expect(
        page.getByRole("button", { name: "Jump to…" }),
      ).toBeVisible();
    }
  });
}
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
