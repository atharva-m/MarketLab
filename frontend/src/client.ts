import { parse } from "lossless-json";

export type Data = Record<string, any>;
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export function exactParse(text: string): any {
  return parse(text, undefined, (token) => {
    const value = Number(token);
    return /^-?\d+$/.test(token) && Number.isSafeInteger(value) ? value : token;
  });
}
export async function request(
  path: string,
  options: RequestInit = {},
): Promise<{ data: Data; cache: string | null }> {
  if (!path.startsWith("/v1/") && !path.startsWith("/health/"))
    throw new Error("Invalid local API path");
  const expensiveRead =
    path.startsWith("/v1/bars?") || /^\/v1\/datasets\/[a-f0-9]{64}$/.test(path);
  const timeout = AbortSignal.timeout(
    options.method === "POST" || expensiveRead ? 1_860_000 : 30_000,
  );
  const signal = options.signal
    ? AbortSignal.any([options.signal, timeout])
    : timeout;
  const response = await fetch(path, {
    ...options,
    signal,
    credentials: "same-origin",
    redirect: "error",
  });
  const text = await response.text();
  let data: Data;
  try {
    data = exactParse(text) as Data;
  } catch {
    throw new ApiError(
      "The API returned an unreadable response.",
      response.status,
    );
  }
  if (!response.ok)
    throw new ApiError(
      typeof data.detail === "string" ? data.detail : "The operation failed.",
      response.status,
    );
  return { data, cache: response.headers.get("X-Cache") };
}
export type Operation = {
  id: string;
  slot: string;
  path: string;
  body: string;
  key: string;
  state: "uncertain" | "resolved";
  result?: Data;
  created: number;
};
const STORAGE = "marketlab.operations.v1";
export function operations(): Operation[] {
  try {
    const values = JSON.parse(
      localStorage.getItem(STORAGE) ?? "[]",
    ) as Operation[];
    return Array.isArray(values)
      ? values
          .filter(
            (v) =>
              typeof v.key === "string" &&
              typeof v.body === "string" &&
              new TextEncoder().encode(v.body).length <= 65536,
          )
          .slice(-20)
      : [];
  } catch {
    return [];
  }
}
function save(values: Operation[]) {
  localStorage.setItem(STORAGE, JSON.stringify(values));
}
export function storedOperation(slot: string) {
  return operations().findLast((v) => v.slot === slot);
}
export function prepareOperation(
  slot: string,
  path: string,
  body: string,
): Operation {
  if (new TextEncoder().encode(body).length > 65536)
    throw new Error("Submission exceeds 64 KiB.");
  const values = operations();
  const existing = values.findLast((v) => v.slot === slot);
  if (existing?.state === "uncertain") {
    if (existing.path !== path || existing.body !== body)
      throw new Error(
        "An unresolved operation has a different saved body. Retry it or explicitly discard it first.",
      );
    return existing;
  }
  if (values.length >= 20 && values.every((v) => v.state === "uncertain"))
    throw new Error(
      "Twenty unresolved operations are saved. Resolve or explicitly discard one before submitting.",
    );
  const op: Operation = {
    id: crypto.randomUUID(),
    slot,
    path,
    body,
    key: `ui.${crypto.randomUUID()}`,
    state: "uncertain",
    created: Date.now(),
  };
  const keep =
    values.length >= 20
      ? values.filter((v) => v !== values.find((v) => v.state === "resolved"))
      : values;
  save([...keep, op]);
  return op;
}
export function discardOperation(id: string) {
  save(operations().filter((v) => v.id !== id));
}
export async function sendOperation(op: Operation): Promise<Data> {
  const { data } = await request(op.path, {
    method: "POST",
    headers: op.body
      ? { "Content-Type": "application/json", "Idempotency-Key": op.key }
      : {},
    body: op.body || undefined,
  });
  save(
    operations().map((v) =>
      v.id === op.id ? { ...v, state: "resolved", result: data } : v,
    ),
  );
  return data;
}
export const versionPattern = /^[a-f0-9]{64}$/;
export function versionIDs(text: string): string[] {
  const values = text.split(/[\s,]+/).filter(Boolean);
  if (
    !values.length ||
    values.length > 62 ||
    values.some((v) => !versionPattern.test(v)) ||
    new Set(values).size !== values.length
  )
    throw new Error("Choose 1–62 unique full lowercase dataset version IDs.");
  return [...values].sort();
}
export function utc(value: string): string {
  if (
    !/^2025-01-\d{2}T\d{2}:\d{2}:00Z$/.test(value) &&
    value !== "2025-02-01T00:00:00Z"
  )
    throw new Error(
      "Use an explicit January UTC timestamp, for example 2025-01-01T01:00:00Z.",
    );
  const time = Date.parse(value);
  if (
    !Number.isFinite(time) ||
    new Date(time).toISOString().replace(".000Z", "Z") !== value ||
    time % 300000 !== 0
  )
    throw new Error("Timestamp must be valid UTC and aligned to five minutes.");
  return value;
}
export function researchSpec(form: Data, versions: string[]): Data {
  const start = utc(form.start);
  const end = utc(form.end);
  const history = utc(form.history_start);
  if (!(history < start && start < end))
    throw new Error(
      "History must precede evaluation start, and evaluation end must follow start.",
    );
  const workflow = form.workflow;
  const symbols =
    workflow === "cross_asset" ? ["BTCUSDT", "ETHUSDT"] : [form.symbol];
  const allowed =
    workflow === "market_profile"
      ? ["profile"]
      : workflow === "cross_asset"
        ? ["profile", "correlation", "close_change_difference"]
        : ["profile", "clusters"];
  const metrics = (form.metrics as string[]).filter((v) => allowed.includes(v));
  if (!metrics.length) throw new Error("Select at least one metric.");
  return {
    schema: "research-spec-v1",
    workflow,
    symbols,
    dataset_versions: versions,
    start,
    end,
    history_start: history,
    interval: "5m",
    metrics: [...metrics].sort(),
    parameters: {},
    predicates:
      workflow === "volatility_cluster"
        ? { volatility_quantile: "0.9", volume_multiple: "2", min_bars: 2 }
        : {},
  };
}
export function selectedVersions(): Data[] {
  try {
    return JSON.parse(
      localStorage.getItem("marketlab.versions.v1") ?? "[]",
    ) as Data[];
  } catch {
    return [];
  }
}
export function setSelectedVersions(rows: Data[]) {
  localStorage.setItem(
    "marketlab.versions.v1",
    JSON.stringify(rows.slice(0, 62)),
  );
}
