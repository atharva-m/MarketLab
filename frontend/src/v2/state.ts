import type { Data } from "../client";
import type { Dataset, Instrument } from "./api";

const SELECTED = "marketlab.v2.selection";
const HASH = /^[a-f0-9]{64}$/;
export const instrumentLabel = (v: Instrument) =>
  `${v.display_name} · Binance spot · ${v.base_asset}/${v.quote_asset}${v.enabled ? "" : " · retained only"}`;
export function selected(): Dataset[] {
  try {
    const rows = JSON.parse(localStorage.getItem(SELECTED) ?? "[]");
    return Array.isArray(rows)
      ? rows
          .filter(
            (v) =>
              v &&
              HASH.test(v.dataset_version_id) &&
              typeof v.instrument_id === "string" &&
              /^\d{4}-\d{2}-\d{2}$/.test(v.trade_date),
          )
          .slice(0, 62)
      : [];
  } catch {
    return [];
  }
}
export function saveSelection(rows: Dataset[]) {
  if (rows.length > 62) throw new Error("Select at most 62 daily versions.");
  const days = new Set<string>();
  for (const row of rows) {
    const day = `${row.instrument_id}/${row.trade_date}`;
    if (days.has(day))
      throw new Error("Choose one alternative for each instrument/day.");
    days.add(day);
  }
  // Store only identity and bounded metadata for an explicit selection.
  localStorage.setItem(
    SELECTED,
    JSON.stringify(
      rows.map((row) => ({
        dataset_version_id: row.dataset_version_id,
        instrument_id: row.instrument_id,
        trade_date: row.trade_date,
        row_count: row.row_count,
        contract: row.contract,
      })),
    ),
  );
}
export function utc(value: string, minutes = 5): number {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00(?:Z|\+00:00)$/.test(value))
    throw new Error(
      "Use explicit UTC timestamps, for example YYYY-MM-DDT01:00:00Z.",
    );
  const n = Date.parse(value);
  if (!Number.isFinite(n) || n % (minutes * 60000))
    throw new Error(
      `Timestamps must align to ${minutes}-minute UTC boundaries.`,
    );
  // Date.parse normalizes invalid dates such as February 30; reject those.
  if (new Date(n).toISOString().slice(0, 19) !== value.slice(0, 19))
    throw new Error("Use a real UTC calendar date.");
  return n;
}
export function daysBetween(first: string, before: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(first) || !/^\d{4}-\d{2}-\d{2}$/.test(before))
    throw new Error("Choose UTC dates.");
  const start = utc(`${first}T00:00:00Z`),
    end = utc(`${before}T00:00:00Z`);
  if (end <= start)
    throw new Error("The exclusive end date must follow the start date.");
  return (end - start) / 86400000;
}
export function researchSpec(
  form: Data,
  rows: Dataset[],
  instruments: Instrument[],
  limits: Data = {},
) {
  const ids: string[] = [...new Set<string>(form.instrument_ids)].sort();
  const cross = form.workflow === "cross_asset";
  if (ids.length !== (cross ? 2 : 1))
    throw new Error(
      cross ? "Choose exactly two instruments." : "Choose one instrument.",
    );
  if (!rows.length || rows.length > (limits.partitions ?? 62))
    throw new Error("Pin 1–62 daily versions, including history.");
  const metadata = ids.map((id) =>
    instruments.find((v) => v.instrument_id === id),
  );
  if (metadata.some((v) => !v))
    throw new Error("Refresh metadata for every selected instrument.");
  if (cross && metadata[0]!.quote_asset !== metadata[1]!.quote_asset)
    throw new Error(
      "Comparison requires identical quote assets; currency conversion is unavailable.",
    );
  const history = utc(form.history_start),
    start = utc(form.start),
    end = utc(form.end);
  if (!(history < start && start < end))
    throw new Error(
      "Require history start < evaluation start < exclusive end.",
    );
  const expected = ((end - history) / 300000) * ids.length;
  if (expected > (limits.research_buckets ?? 17856))
    throw new Error(
      "Selection exceeds the five-minute bucket limit including history across instruments.",
    );
  const warmup = form.workflow === "volatility_cluster" ? 300 : 12;
  if ((start - history) / 300000 < warmup)
    throw new Error(
      `Provide at least ${warmup} preceding five-minute bars; actual eligibility is checked by the server.`,
    );
  const required = new Set<string>();
  for (
    let at = Math.floor(history / 86400000) * 86400000;
    at < end;
    at += 86400000
  )
    for (const id of ids)
      required.add(`${id}/${new Date(at).toISOString().slice(0, 10)}`);
  if (required.size > 62)
    throw new Error(
      "Selection touches more than 62 instrument/day partitions.",
    );
  const seen = new Set<string>();
  for (const row of rows) {
    const day = `${row.instrument_id}/${row.trade_date}`;
    if (!required.has(day))
      throw new Error(
        "Remove versions outside the selected instruments/history/evaluation dates.",
      );
    if (seen.has(day))
      throw new Error(
        "Resolve alternative versions: pin exactly one per instrument/day.",
      );
    seen.add(day);
  }
  if (seen.size !== required.size)
    throw new Error(
      "Registered daily selection is incomplete, including warm-up history.",
    );
  if (!Array.isArray(form.metrics) || !form.metrics.length)
    throw new Error("Choose at least one supported metric.");
  return {
    schema: "research-spec-v2",
    workflow: form.workflow,
    instrument_ids: ids,
    dataset_versions: rows.map((v) => v.dataset_version_id).sort(),
    history_start: form.history_start,
    start: form.start,
    end: form.end,
    interval: "5m",
    metrics: [...form.metrics].sort(),
    parameters: {},
    predicates:
      form.workflow === "volatility_cluster"
        ? { volatility_quantile: "0.9", volume_multiple: "2", min_bars: 2 }
        : {},
  };
}

export function suggestedWindow(
  coverage: Data[],
  workflow: string,
  limits: Data = {},
): Data | null {
  if (!coverage.length || coverage.some((v) => !Array.isArray(v.days)))
    return null;
  if (
    coverage.some((body) =>
      body.days.some(
        (day: Data) =>
          day.next_cursor ||
          day.observed_bounds_complete !== true ||
          day.versions.length > 1,
      ),
    )
  )
    return null;
  const warmup = workflow === "volatility_cluster" ? 300 : 12;
  const common = new Map<string, Dataset[]>();
  for (const day of coverage[0].days) {
    const peers = coverage.map((v) =>
      v.days.find((d: Data) => d.date === day.date),
    );
    if (
      peers.every(
        (d) =>
          d &&
          d.observed_bounds_complete === true &&
          !d.next_cursor &&
          d.versions.length === 1,
      )
    )
      common.set(
        day.date,
        peers.map((d) => d.versions[0]),
      );
  }
  const dates = [...common.keys()].sort();
  if (!dates.length) return null;
  // Latest contiguous interval is deterministic only when each touched day is
  // unambiguous and the metadata response explicitly confirms completeness.
  const last = dates.at(-1)!;
  const latest = [last];
  const maxDays = Math.min(
    Math.floor((limits.partitions ?? 62) / coverage.length),
    Math.floor((limits.research_buckets ?? 17856) / (288 * coverage.length)),
  );
  for (let i = dates.length - 2; i >= 0 && latest.length < maxDays; i--) {
    if (
      Date.parse(`${latest[0]}T00:00:00Z`) -
        Date.parse(`${dates[i]}T00:00:00Z`) !==
      86400000
    )
      break;
    latest.unshift(dates[i]);
  }
  const from = `${latest[0]}T00:00:00Z`;
  const start = new Date(Date.parse(from) + warmup * 300000)
    .toISOString()
    .replace(".000Z", "Z");
  const end = new Date(Date.parse(`${last}T00:00:00Z`) + 86400000)
    .toISOString()
    .replace(".000Z", "Z");
  if (Date.parse(start) >= Date.parse(end)) return null;
  return {
    history_start: from,
    start,
    end,
    rows: latest.flatMap((day) => common.get(day)!),
  };
}
