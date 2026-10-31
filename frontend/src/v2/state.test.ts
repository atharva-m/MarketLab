import { afterEach, expect, it } from "vitest";
import {
  researchSpec,
  saveSelection,
  selected,
  suggestedWindow,
  utc,
} from "./state";
import type { Dataset, Instrument } from "./api";
import { chartSegments } from "./Workspace";

afterEach(() => localStorage.clear());
const instrument = (id: string, quote = "USDT") =>
  ({
    instrument_id: `binance:spot:${id}`,
    display_name: id,
    source_symbol: id,
    base_asset: id,
    quote_asset: quote,
    enabled: true,
    revision: 0,
  }) as Instrument;
const sol = instrument("SOLUSDT");
const btc = instrument("BTCUSDT");
const row = (id = sol.instrument_id, day = "2025-03-01", hash = "a") =>
  ({
    instrument_id: id,
    trade_date: day,
    dataset_version_id: hash.repeat(64),
    row_count: "9223372036854775807",
    contract: "dataset-manifest-v2",
  }) as Dataset;
const form = () => ({
  workflow: "market_profile",
  instrument_ids: [sol.instrument_id],
  history_start: "2025-03-01T00:00:00Z",
  start: "2025-03-01T01:00:00Z",
  end: "2025-03-02T00:00:00Z",
  metrics: ["profile"],
});

it("builds exact pinned v2 requests for non-January instruments and preserves large count metadata", () => {
  const spec = researchSpec(form(), [row()], [sol]);
  expect(spec).toEqual({
    ...form(),
    schema: "research-spec-v2",
    dataset_versions: ["a".repeat(64)],
    interval: "5m",
    parameters: {},
    predicates: {},
  });
  saveSelection([row()]);
  expect(selected()[0].row_count).toBe("9223372036854775807");
  expect(() =>
    saveSelection([row(), row(sol.instrument_id, "2025-03-01", "b")]),
  ).toThrow("alternative");
});

it("rejects missing history, quote mismatch, extra days, alternatives and excessive combined buckets", () => {
  expect(() => researchSpec(form(), [], [sol])).toThrow("Pin");
  expect(() =>
    researchSpec({ ...form(), start: "2025-03-01T00:55:00Z" }, [row()], [sol]),
  ).toThrow("12");
  expect(() =>
    researchSpec({ ...form(), workflow: "volatility_cluster" }, [row()], [sol]),
  ).toThrow("300");
  expect(() =>
    researchSpec(
      form(),
      [row(), row(sol.instrument_id, "2025-03-02", "b")],
      [sol],
    ),
  ).toThrow("outside");
  expect(() =>
    researchSpec(
      form(),
      [row(), row(sol.instrument_id, "2025-03-01", "b")],
      [sol],
    ),
  ).toThrow("alternative");
  expect(() =>
    researchSpec(
      {
        ...form(),
        workflow: "cross_asset",
        instrument_ids: [sol.instrument_id, btc.instrument_id],
      },
      [row(), row(btc.instrument_id, "2025-03-01", "b")],
      [sol, { ...btc, quote_asset: "USD" }],
    ),
  ).toThrow("identical quote");
  expect(() =>
    researchSpec({ ...form(), end: "2025-06-01T00:00:00Z" }, [row()], [sol]),
  ).toThrow("bucket limit");
});

it("requires real, explicitly UTC and aligned timestamps", () => {
  for (const invalid of [
    "2025-02-30T00:00:00Z",
    "2025-03-01T00:01:00Z",
    "2025-03-01T00:00:00",
    "2025-03-01T00:00:00-05:00",
  ])
    expect(() => utc(invalid)).toThrow();
  expect(utc("2025-03-01T00:00:00+00:00")).toBe(Date.UTC(2025, 2, 1));
});

it("suggests only complete unambiguous coverage and does not skip alternatives to invent a default", () => {
  const coverage = {
    instrument_id: sol.instrument_id,
    days: [
      {
        date: "2025-03-01",
        versions: [row()],
        observed_bounds_complete: true,
        next_cursor: null,
      },
    ],
  };
  expect(suggestedWindow([coverage], "market_profile")?.start).toBe(
    "2025-03-01T01:00:00Z",
  );
  expect(suggestedWindow([coverage], "volatility_cluster")).toBeNull();
  expect(
    suggestedWindow(
      [
        {
          ...coverage,
          days: [
            {
              ...coverage.days[0],
              versions: [row(), row(sol.instrument_id, "2025-03-01", "b")],
            },
          ],
        },
      ],
      "market_profile",
    ),
  ).toBeNull();
  expect(
    suggestedWindow(
      [
        {
          ...coverage,
          days: [
            {
              ...coverage.days[0],
              next_cursor: "opaque",
              observed_bounds_complete: false,
            },
          ],
        },
      ],
      "market_profile",
    ),
  ).toBeNull();
});

it("disconnects chart paths across missing/null bars instead of filling gaps", () => {
  const segments = chartSegments(
    [
      { start: "2025-03-01T00:00:00Z", close: "10" },
      { start: "2025-03-01T00:05:00Z", close: "11" },
      { start: "2025-03-01T00:10:00Z", close: null },
      { start: "2025-03-01T00:15:00Z", close: "13" },
    ],
    "5m",
    "2025-03-01T00:00:00Z",
    "2025-03-01T00:20:00Z",
  );
  expect(segments).toHaveLength(2);
  expect(segments[0]).toContain(" L");
  expect(segments[1]).not.toContain(" L");
});
