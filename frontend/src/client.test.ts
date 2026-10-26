import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  exactParse,
  prepareOperation,
  discardOperation,
  operations,
  researchSpec,
  sendOperation,
  versionIDs,
  utc,
} from "./client";
import { candleRises, chartRequest } from "./Chart";
beforeEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});
describe("exact numerical presentation", () => {
  it("uses exact decimal candle direction below the binary float ULP", () => {
    expect(
      candleRises(
        "10000000000000000000.000000000000000002",
        "10000000000000000000.000000000000000001",
      ),
    ).toBe(false);
    expect(candleRises("0.000000000000000001", "0.000000000000000002")).toBe(
      true,
    );
  });
  it("preserves int64 lexemes and fixed decimals without float conversion", () => {
    expect(
      exactParse(
        '{"count":9223372036854775807,"v":"0.000000000000000001","safe":3,"nil":null}',
      ),
    ).toEqual({
      count: "9223372036854775807",
      v: "0.000000000000000001",
      safe: 3,
      nil: null,
    });
  });
  it("does not reinterpret missing statistics as zero", () => {
    expect(
      exactParse(
        '{"value":null,"reason":"zero_variance","observation_count":2}',
      ),
    ).toEqual({ value: null, reason: "zero_variance", observation_count: 2 });
  });
});
describe("durable browser operation journal", () => {
  it("retains exact body/key after lost response and refuses edits", async () => {
    const op = prepareOperation("research", "/v1/research/runs", '{"a":1}');
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("network lost")),
    );
    await expect(sendOperation(op)).rejects.toThrow("network lost");
    expect(
      prepareOperation("research", "/v1/research/runs", '{"a":1}').key,
    ).toBe(op.key);
    expect(() =>
      prepareOperation("research", "/v1/research/runs", '{"a":2}'),
    ).toThrow("different saved body");
    expect(operations()[0].state).toBe("uncertain");
  });
  it("resolves successful operations and starts a deliberate fresh key", async () => {
    const op = prepareOperation("research", "/v1/research/runs", "{}");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('{"run_id":"r"}', {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await sendOperation(op);
    expect(operations()[0].state).toBe("resolved");
    expect(
      prepareOperation("research", "/v1/research/runs", "{}").key,
    ).not.toBe(op.key);
  });
  it("does not silently evict unresolved keys and enforces UTF8 body cap", () => {
    for (let i = 0; i < 20; i++)
      prepareOperation(String(i), "/v1/research/runs", "{}");
    expect(() => prepareOperation("next", "/v1/research/runs", "{}")).toThrow(
      "Twenty unresolved",
    );
    discardOperation(operations()[0].id);
    expect(prepareOperation("next", "/v1/research/runs", "{}")).toBeDefined();
    expect(() =>
      prepareOperation("large", "/v1/research/runs", "é".repeat(32769)),
    ).toThrow("64 KiB");
  });
});
describe("explicit research and chart bounds", () => {
  const versions = ["b".repeat(64), "a".repeat(64)];
  it("rejects duplicate or malformed versions without choosing latest", () => {
    expect(versionIDs(versions.join("\n"))).toEqual([...versions].sort());
    expect(() => versionIDs(versions[0] + " " + versions[0])).toThrow("unique");
    expect(() => versionIDs("latest")).toThrow("full lowercase");
  });
  it("pins cross asset fields and separates history", () => {
    const spec = researchSpec(
      {
        workflow: "cross_asset",
        start: "2025-01-01T01:00:00Z",
        end: "2025-01-02T00:00:00Z",
        history_start: "2025-01-01T00:00:00Z",
        metrics: ["correlation"],
      },
      versions,
    );
    expect(spec.symbols).toEqual(["BTCUSDT", "ETHUSDT"]);
    expect(spec.predicates).toEqual({});
    expect(spec.metrics).toEqual(["correlation"]);
    expect(spec.interval).toBe("5m");
  });
  it("rejects invalid day and five-minute research misalignment", () => {
    expect(() => utc("2025-01-32T00:00:00Z")).toThrow();
    expect(() => utc("2025-01-01T00:01:00Z")).toThrow("five minutes");
  });
  it("accepts one-minute boundaries while enforcing chart1440 cap", () => {
    expect(
      chartRequest(
        "BTCUSDT",
        "1m",
        "2025-01-01T00:01:00Z",
        "2025-01-01T00:02:00Z",
        [versions[0]],
      ),
    ).toContain("interval=1m");
    expect(() =>
      chartRequest(
        "BTCUSDT",
        "1m",
        "2025-01-01T00:00:00Z",
        "2025-01-03T00:00:00Z",
        versions,
      ),
    ).toThrow("1,440");
    expect(() =>
      chartRequest(
        "BTCUSDT",
        "5m",
        "2025-01-01T00:01:00Z",
        "2025-01-01T00:06:00Z",
        versions,
      ),
    ).toThrow("aligned");
  });
});
