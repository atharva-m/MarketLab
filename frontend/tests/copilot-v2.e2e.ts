import { test, expect, type Page, type Route } from "@playwright/test";

// Mocked browser contract coverage, separate from actual model/data acceptance.
const id = "77777777-7777-4777-8777-777777777777";
const run = "44444444-4444-4444-8444-444444444444";
const instrument = "binance:spot:SOLUSDT";
const version = "d".repeat(64);
const dataset = {
  instrument_id: instrument,
  dataset_version_id: version,
  trade_date: "2025-03-01",
  row_count: 10,
  contract: "dataset-manifest-v2",
};
const json = (route: Route, data: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(data),
  });
async function base(page: Page) {
  await page.route("**/v1/**", (route) =>
    json(route, { items: [], next_cursor: null }),
  );
  await page.route("**/v2/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/v2/")) return route.fallback();
    if (path === "/v2/capabilities")
      return json(route, {
        copilot_available: true,
        memo_available: true,
        limits: {},
      });
    return json(
      route,
      { error: { code: "not_found", message: "Not found" } },
      404,
    );
  });
}
const clarificationStatus = (revision: number) => ({
  schema: "copilot-status-v2",
  request_id: id,
  current_revision: revision,
  state: "succeeded",
  outcome: "needs_clarification",
  run_id: null,
  snapshot: {
    instruments: {
      i0: {
        instrument_id: instrument,
        source_symbol: "SOLUSDT",
        base_asset: "SOL",
        quote_asset: "USDT",
      },
    },
  },
  revisions: [
    {
      revision,
      state: "succeeded",
      outcome: "needs_clarification",
      model_calls: 1,
      questions: [
        { field: "meaning", question: `Clarify revision ${revision}.` },
      ],
    },
  ],
});
test("selected copilot creates exact context, recovers questions and submits a fenced answer", async ({
  page,
}) => {
  await base(page);
  let revision = 0;
  let create: any;
  let answer: any;
  let key = "";
  await page.route("**/v2/copilot/requests", (route) => {
    create = route.request().postDataJSON();
    key = route.request().headers()["idempotency-key"];
    return json(route, { request_id: id, revision: 0, replayed: false }, 201);
  });
  await page.route(`**/v2/copilot/requests/${id}`, (route) =>
    json(route, {
      schema: "copilot-status-v2",
      request_id: id,
      current_revision: revision,
      state: "succeeded",
      outcome: revision ? "submitted" : "needs_clarification",
      run_id: revision ? run : null,
      snapshot: {
        instruments: {
          i0: {
            instrument_id: instrument,
            source_symbol: "SOLUSDT",
            base_asset: "SOL",
            quote_asset: "USDT",
          },
        },
        datasets: [dataset],
      },
      revisions: [
        {
          revision: 0,
          state: "succeeded",
          outcome: "needs_clarification",
          model_calls: 1,
          questions: [
            {
              field: "start",
              question: "<img src=x onerror=alert(1)> Which UTC start?",
            },
          ],
        },
        ...(revision
          ? [
              {
                revision: 1,
                state: "succeeded",
                outcome: "submitted",
                model_calls: 1,
                questions: null,
              },
            ]
          : []),
      ],
    }),
  );
  await page.route(`**/v2/copilot/requests/${id}/clarifications`, (route) => {
    answer = route.request().postDataJSON();
    revision = 1;
    return json(route, { request_id: id, revision: 1, replayed: false });
  });
  await page.goto("/#/v2/copilot/new");
  await page.evaluate(
    (pin) =>
      localStorage.setItem("marketlab.v2.selection", JSON.stringify([pin])),
    dataset,
  );
  await page.reload();
  await page
    .getByLabel("Research request", { exact: true })
    .fill("Profile SOLUSDT; ask me for the missing UTC fields.");
  await page
    .getByRole("checkbox", { name: /I confirm these exact selected/ })
    .check();
  await page
    .getByRole("button", { name: "Submit selected-context request" })
    .click();
  await expect(page).toHaveURL(new RegExp(`/v2/copilot/${id}`));
  expect(create).toEqual({
    schema: "copilot-request-v2",
    text: "Profile SOLUSDT; ask me for the missing UTC fields.",
    context: {},
    instrument_ids: [instrument],
    dataset_versions: [version],
  });
  expect(key).toMatch(/^v2ui\./);
  await expect(page.getByText(/Which UTC start/)).toBeVisible();
  expect(await page.locator("img").count()).toBe(0);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Answer clarification · 1/5" }),
  ).toBeVisible();
  await page
    .getByLabel("Clarification answer")
    .fill("Start 2025-03-01T01:00:00Z");
  await page
    .getByRole("button", { name: "Submit clarification answer" })
    .click();
  await expect(
    page.getByRole("link", { name: "Open linked numerical result" }),
  ).toHaveAttribute("href", `#/v2/runs/${run}`);
  expect(answer).toEqual({
    schema: "copilot-answer-v2",
    expected_revision: 0,
    text: "Start 2025-03-01T01:00:00Z",
    context: {},
  });
  expect(
    await page
      .getByRole("button", { name: "Submit clarification answer" })
      .count(),
  ).toBe(0);
  const stored = await page.evaluate(() => JSON.stringify(localStorage));
  expect(stored).not.toContain("Profile SOLUSDT");
  expect(stored).not.toContain("Which UTC start");
});

test("empty selection stays explicit, and revision five is readable without another answer", async ({
  page,
}) => {
  await base(page);
  await page.goto("/#/v2/copilot/new");
  await expect(
    page.getByRole("button", { name: "Submit selected-context request" }),
  ).toBeDisabled();
  await page.route(`**/v2/copilot/requests/${id}`, (route) =>
    json(route, {
      request_id: id,
      current_revision: 5,
      state: "succeeded",
      outcome: "needs_clarification",
      run_id: null,
      snapshot: {},
      revisions: [
        {
          revision: 5,
          state: "succeeded",
          outcome: "needs_clarification",
          model_calls: 1,
          questions: [{ field: "meaning", question: "Please clarify." }],
        },
      ],
    }),
  );
  await page.getByLabel("Copilot request ID", { exact: true }).fill(id);
  await page.getByRole("button", { name: "Open copilot request" }).click();
  await expect(page.getByText(/Five answers have been accepted/)).toBeVisible();
  await expect(page.getByLabel("Clarification answer")).toHaveCount(0);
  await expect(
    page.getByText("meaning: Please clarify.", { exact: true }),
  ).toBeVisible();
});

test("an uncertain create retries the same operation and surfaces safe errors", async ({
  page,
}) => {
  await base(page);
  const keys: string[] = [];
  const bodies: unknown[] = [];
  await page.route("**/v2/copilot/requests", (route) => {
    keys.push(route.request().headers()["idempotency-key"]);
    bodies.push(route.request().postDataJSON());
    return json(
      route,
      {
        error: {
          code: "unavailable",
          message: "Catalog temporarily unavailable",
        },
      },
      503,
    );
  });
  await page.goto("/#/v2/copilot/new");
  await page.evaluate(
    (pin) =>
      localStorage.setItem("marketlab.v2.selection", JSON.stringify([pin])),
    dataset,
  );
  await page.reload();
  await page
    .getByLabel("Research request", { exact: true })
    .fill("Profile this selection");
  await page
    .getByRole("checkbox", { name: /I confirm these exact selected/ })
    .check();
  await page
    .getByRole("button", { name: "Submit selected-context request" })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Catalog temporarily unavailable",
  );
  await page
    .getByRole("button", { name: "Submit selected-context request" })
    .click();
  await expect.poll(() => keys.length).toBe(2);
  expect(keys[0]).toBe(keys[1]);
  expect(bodies[0]).toEqual(bodies[1]);
  await expect(
    page.getByRole("link", { name: "Open manual numerical research" }),
  ).toBeVisible();
});

test("a lost accepted-answer response retries the identical operation without another revision", async ({
  page,
}) => {
  await base(page);
  let revision = 0;
  let accepted = 0;
  const keys: string[] = [];
  const bodies: unknown[] = [];
  await page.route(`**/v2/copilot/requests/${id}`, (route) =>
    json(route, clarificationStatus(revision)),
  );
  await page.route(`**/v2/copilot/requests/${id}/clarifications`, (route) => {
    keys.push(route.request().headers()["idempotency-key"]);
    bodies.push(route.request().postDataJSON());
    if (keys.length === 1) {
      revision = 1;
      accepted++;
      return route.abort("failed"); // Server accepted; browser lost the response.
    }
    return json(route, { request_id: id, revision: 1, replayed: true });
  });
  await page.goto(`/#/v2/copilot/${id}`);
  await page
    .getByLabel("Clarification answer")
    .fill("Use the selected SOLUSDT profile");
  await page
    .getByRole("button", { name: "Submit clarification answer" })
    .click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Clarification answer")).toHaveValue(
    "Use the selected SOLUSDT profile",
  );
  await page
    .getByRole("button", { name: "Submit clarification answer" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Answer clarification · 2/5" }),
  ).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  expect(bodies[0]).toEqual(bodies[1]);
  expect(bodies[0]).toEqual({
    schema: "copilot-answer-v2",
    expected_revision: 0,
    text: "Use the selected SOLUSDT profile",
    context: {},
  });
  expect(accepted).toBe(1);
  await expect(page.getByLabel("Clarification answer")).toHaveValue("");
});

test("stale-answer conflict recovers the current revision before a new answer", async ({
  page,
}) => {
  await base(page);
  let revision = 0;
  let accepted = 0;
  const bodies: any[] = [];
  const keys: string[] = [];
  await page.route(`**/v2/copilot/requests/${id}`, (route) =>
    json(route, clarificationStatus(revision)),
  );
  await page.route(`**/v2/copilot/requests/${id}/clarifications`, (route) => {
    bodies.push(route.request().postDataJSON());
    keys.push(route.request().headers()["idempotency-key"]);
    if (bodies.length === 1) {
      revision = 1; // A concurrent client already answered revision zero.
      return json(
        route,
        {
          error: {
            code: "conflict",
            message: "Clarification revision is stale",
          },
        },
        409,
      );
    }
    revision = 2;
    accepted++;
    return json(route, { request_id: id, revision, replayed: false });
  });
  await page.goto(`/#/v2/copilot/${id}`);
  await page.getByLabel("Clarification answer").fill("Stale answer");
  await page
    .getByRole("button", { name: "Submit clarification answer" })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Clarification revision is stale",
  );
  expect(accepted).toBe(0);
  await page.getByRole("button", { name: "Refresh copilot status" }).click();
  await expect(
    page.getByRole("heading", { name: "Answer clarification · 2/5" }),
  ).toBeVisible();
  await expect(page.getByLabel("Clarification answer")).toHaveValue("");
  await page
    .getByLabel("Clarification answer")
    .fill("Answer the current question");
  await page
    .getByRole("button", { name: "Submit clarification answer" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Answer clarification · 3/5" }),
  ).toBeVisible();
  expect(bodies.map((body) => body.expected_revision)).toEqual([0, 1]);
  expect(keys[0]).not.toBe(keys[1]);
  expect(accepted).toBe(1);
  await expect(
    page.getByRole("link", { name: "Open linked numerical result" }),
  ).toHaveCount(0);
});

test("memo enqueue and plain-text reading remain supplemental to exact numerical results", async ({
  page,
}) => {
  await base(page);
  let queued = false;
  let body: any;
  await page.route(`**/v2/research/runs/${run}`, (route) =>
    json(route, {
      state: "succeeded",
      revision: 0,
      attempt_count: 1,
      numerical_available: true,
      spec: {
        workflow: "market_profile",
        interval: "5m",
        instrument_ids: [instrument],
        history_start: "2025-03-01T00:00:00Z",
        start: "2025-03-01T01:00:00Z",
        end: "2025-03-02T00:00:00Z",
      },
      fingerprint: {
        instruments: {
          [instrument]: {
            instrument_id: instrument,
            display_name: "SOL",
            base_asset: "SOL",
            quote_asset: "USDT",
          },
        },
        datasets: [dataset],
      },
      attempts: [],
    }),
  );
  await page.route(`**/v2/research/runs/${run}/summary`, (route) =>
    json(route, { quote_volume: "1.123456789012345678" }),
  );
  await page.route(`**/v2/research/runs/${run}/memo`, (route) => {
    if (route.request().method() === "POST") {
      body = route.request().postDataJSON();
      queued = true;
      return json(route, { run_id: run, state: "queued", model_calls: 0 });
    }
    return queued
      ? json(route, {
          schema: "memo-status-v2",
          run_id: run,
          state: "succeeded",
          model_calls: 1,
          error_code: null,
          memo: "<script>alert(1)</script> is literal text.\n\n**A grounded second paragraph.**\n\nA grounded third paragraph.",
          numerical_manifest_sha256: "a".repeat(64),
          summary_sha256: "b".repeat(64),
        })
      : json(
          route,
          { error: { code: "not_found", message: "Missing memo" } },
          404,
        );
  });
  await page.goto(`/#/v2/runs/${run}`);
  await expect(
    page.getByText("1.123456789012345678", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Queue supplemental memo" }).click();
  expect(body).toEqual({ schema: "memo-request-v2" });
  await expect(page.locator(".v2-memo-text > p")).toHaveCount(3);
  await expect(page.locator(".v2-memo-text script")).toHaveCount(0);
  await expect(
    page.getByText("**A grounded second paragraph.**", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("1.123456789012345678", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Pinned dataset charts" }),
  ).toBeVisible();
});
