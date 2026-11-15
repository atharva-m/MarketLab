import { expect, test, type Page, type Route } from "@playwright/test";

const run = "44444444-4444-4444-8444-444444444444";
const submission = "55555555-5555-4555-8555-555555555555";
const copilot = "66666666-6666-4666-8666-666666666666";
const windows = "77777777-7777-4777-8777-777777777777";
const ec2 = "88888888-8888-4888-8888-888888888888";
const windowsHost = "99999999-9999-4999-8999-999999999999";
const ec2Host = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const date = "2025-03-01";
const instant = (minute: number) => `${date}T00:0${minute}:00Z`;
const instrument = "binance:spot:SOLUSDT";
const observed_at = instant(4);
const first = {
  attempt_number: 1,
  worker_instance_id: ec2,
  host_id: ec2Host,
  host_label: "EC2",
  started_at: instant(0),
  ended_at: instant(1),
  outcome: "expired",
  error_code: "lease_lost",
  fencing_token: 1,
  lease_valid: null,
};
const second = {
  ...first,
  attempt_number: 2,
  worker_instance_id: windows,
  host_id: windowsHost,
  host_label: "Windows",
  started_at: instant(1),
  ended_at: instant(2),
  outcome: "succeeded",
  error_code: null,
  fencing_token: 2,
};
const recovered = {
  observed_at,
  attempts: [first, second],
  successful_attempt: 2,
  current_attempt: null,
};
const emptyExecution = {
  observed_at,
  attempts: [],
  successful_attempt: null,
  current_attempt: null,
};

const json = (route: Route, data: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", json: data });

async function base(page: Page) {
  await page.route("**/v1/**", (route) => json(route, { items: [] }));
  await page.route("**/v2/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/v2/")) return route.fallback();
    if (path === "/v2/capabilities")
      return json(route, { memo_available: true, limits: {} });
    if (path === "/v2/instruments") return json(route, { items: [] });
    return json(route, { error: { message: "Not found" } }, 404);
  });
}

const worker = {
  instance_id: windows,
  host_id: windowsHost,
  host_label: "Windows",
  state: "ready",
  fresh: false,
  registered_at: instant(1),
  heartbeat_at: instant(2),
  capabilities: ["research"],
  active_work: [{ kind: "research", identity: run, attempt_number: 2 }],
  active_work_truncated: false,
};

test("research shows the successful worker and links both attempt owners", async ({
  page,
}) => {
  await base(page);
  await page.route(`**/v2/research/runs/${run}`, (route) =>
    json(route, {
      state: "succeeded",
      attempt_count: 2,
      numerical_available: true,
      spec: {
        workflow: "market_profile",
        instrument_ids: [instrument],
        start: instant(0),
        end: instant(2),
        interval: "5m",
      },
      execution_status: recovered,
    }),
  );
  await page.route(`**/v2/research/runs/${run}/summary`, (route) =>
    json(route, {}),
  );
  await page.route(`**/v2/research/runs/${run}/memo`, (route) =>
    json(route, {
      state: "cancelled",
      model_calls: 0,
      execution_status: {
        ...emptyExecution,
        attempts: [
          {
            ...first,
            worker_instance_id: null,
            host_id: null,
            host_label: null,
            outcome: "cancelled",
          },
        ],
      },
    }),
  );
  await page.route(`**/v2/workers?instance_id=${windows}`, (route) =>
    json(route, {
      observed_at,
      items: [{ ...worker, active_work: [] }],
      next_cursor: null,
    }),
  );

  await page.goto(`/#/v2/runs/${run}`);
  const execution = page.getByRole("region", {
    name: "Execution",
    exact: true,
  });
  const primary = execution.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: "1", exact: true }),
  });
  await expect(primary).toContainText("EC2");
  await expect(primary).toContainText("Lease expired");
  await expect(
    primary.getByRole("link", { name: `View worker ${ec2}` }),
  ).toBeVisible();
  const winner = execution
    .getByRole("row")
    .filter({ hasText: "Successful attempt" });
  await expect(winner).toContainText(
    "Recovered on Windows after the lease expired on EC2",
  );
  await execution.getByText("Attempt details").click();
  await expect(execution.getByText("Fence 2")).toBeVisible();
  const memo = page.getByRole("region", { name: "Memo execution" });
  await expect(memo.getByText("Not recorded")).toHaveCount(2);
  await expect(memo.getByText("cancelled", { exact: true })).toBeVisible();
  await winner.getByRole("link", { name: `View worker ${windows}` }).click();
  await expect(
    page.getByRole("table", { name: "Registered workers" }),
  ).toContainText("Windows");
});

test("ingestion distinguishes an unassigned job from an expired or missing claim", async ({
  page,
}) => {
  await base(page);
  await page.route(`**/v2/ingestion/submissions/${submission}`, (route) =>
    json(route, {
      jobs: [
        {
          job_id: run,
          instrument_id: instrument,
          trade_date: date,
          state: "queued",
          attempt_count: 0,
          execution_status: emptyExecution,
        },
        {
          job_id: copilot,
          instrument_id: instrument,
          trade_date: "2025-03-02",
          state: "running",
          attempt_count: 1,
          execution_status: {
            ...emptyExecution,
            attempts: [
              {
                ...first,
                outcome: "running",
                error_code: null,
                ended_at: null,
                lease_valid: false,
              },
            ],
          },
        },
        {
          job_id: windows,
          instrument_id: instrument,
          trade_date: "2025-03-03",
          state: "retry_wait",
          attempt_count: 1,
        },
      ],
    }),
  );
  await page.goto(`/#/v2/submissions/${submission}`);
  const table = page.getByRole("table", { name: "Ingestion jobs" });
  await expect(
    table.getByRole("columnheader", { name: "Host" }).first(),
  ).toBeVisible();
  await expect(
    table.getByRole("columnheader", { name: "Worker" }).first(),
  ).toBeVisible();
  await expect(table.getByRole("row").filter({ hasText: date })).toContainText(
    "Unassigned",
  );
  await page
    .getByRole("button", { name: `Attempts for ${instrument} 2025-03-02` })
    .click();
  const history = page.getByRole("region", { name: "Execution · 2025-03-02" });
  await expect(
    history.getByText("No worker holds a valid lease for this job."),
  ).toBeVisible();
  await expect(history.getByText("Lease expired", { exact: true })).toHaveCount(
    0,
  );
  await page
    .getByRole("button", { name: `Attempts for ${instrument} 2025-03-03` })
    .click();
  await expect(page.getByText("Execution history unavailable.")).toBeVisible();
  await expect(history).toHaveCount(0);
});

test("workers page polls and pages without confusing heartbeat freshness with leases", async ({
  page,
}) => {
  await base(page);
  await page.clock.install();
  let fresh = false;
  await page.route("**/v2/workers?**", (route) => {
    const cursor = new URL(route.request().url()).searchParams.get("cursor");
    if (cursor)
      return json(route, {
        observed_at,
        next_cursor: null,
        items: [
          {
            ...worker,
            instance_id: ec2,
            host_id: ec2Host,
            host_label: "EC2",
            state: "stopped",
            fresh: true,
            active_work: [],
          },
        ],
      });
    return json(route, {
      observed_at,
      items: [{ ...worker, fresh }],
      next_cursor: windows,
    });
  });
  await page.goto("/#/v2/workers");
  const table = page.getByRole("table", { name: "Registered workers" });
  await expect(table.getByText("Stale", { exact: true })).toBeVisible();
  await expect(
    table.getByRole("link", { name: "Research attempt 2" }),
  ).toHaveAttribute("href", `#/v2/runs/${run}`);
  fresh = true;
  await page.clock.fastForward(5100);
  await expect(table.getByText("Fresh", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Next worker page" }).click();
  await expect(table.getByText("EC2", { exact: true })).toBeVisible();
  await expect(table.getByText("stopped", { exact: true })).toBeVisible();
  await expect(table.getByText("Last reported", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Previous worker page" }).click();
  await expect(table.getByText("Windows", { exact: true })).toBeVisible();
});

test("copilot shows each revision’s worker attempts separately from model calls", async ({
  page,
}) => {
  await base(page);
  await page.route(`**/v2/copilot/requests/${copilot}`, (route) =>
    json(route, {
      state: "succeeded",
      outcome: "submitted",
      current_revision: 1,
      run_id: run,
      revisions: [
        {
          revision: 0,
          state: "succeeded",
          outcome: "needs_clarification",
          model_calls: 0,
          execution_status: {
            ...recovered,
            attempts: [{ ...second, attempt_number: 1 }],
            successful_attempt: 1,
          },
        },
        {
          revision: 1,
          state: "succeeded",
          outcome: "submitted",
          model_calls: 0,
          execution_status: {
            ...recovered,
            attempts: [
              first,
              {
                ...second,
                host_id: ec2Host,
                host_label: "EC2",
                worker_instance_id: ec2,
              },
            ],
          },
        },
      ],
    }),
  );
  await page.goto(`/#/v2/copilot/${copilot}`);
  const initial = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: /^Revision 0/ }) });
  const answer = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: /^Revision 1/ }) });
  await expect(
    initial.getByRole("table", { name: "Worker attempts" }),
  ).toContainText("Windows");
  await expect(
    answer.getByRole("table", { name: "Worker attempts" }),
  ).toContainText("Retry on the same host");
  await expect(
    page.getByText("Model calls 0 of 2", { exact: true }),
  ).toHaveCount(2);
  await expect(page.getByRole("link", { name: "Open run" })).toHaveAttribute(
    "href",
    `#/v2/runs/${run}`,
  );
});
