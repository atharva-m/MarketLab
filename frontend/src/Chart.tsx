import { useState } from "react";
import { request, selectedVersions, versionIDs, type Data } from "./client";
import { useResource } from "./hooks";
import { ErrorBox, Tag } from "./components";
export function chartRequest(
  symbol: string,
  interval: string,
  start: string,
  end: string,
  versions: string[],
): string {
  const step = interval === "1m" ? 60000 : 300000;
  for (const value of [start, end]) {
    const time = Date.parse(value);
    if (
      !/^2025-(01-\d{2}|02-01)T\d{2}:\d{2}:00Z$/.test(value) ||
      !Number.isFinite(time) ||
      new Date(time).toISOString().replace(".000Z", "Z") !== value ||
      time % step !== 0 ||
      time < Date.parse("2025-01-01T00:00:00Z") ||
      time > Date.parse("2025-02-01T00:00:00Z")
    )
      throw new Error("Use valid aligned January UTC chart boundaries.");
  }
  const count = (Date.parse(end) - Date.parse(start)) / step;
  if (
    !["1m", "5m"].includes(interval) ||
    !Number.isInteger(count) ||
    count < 1 ||
    count > 1440 ||
    versions.length > 5
  )
    throw new Error(
      "Choose a positive aligned window with at most 1,440 bars: one day at 1m or five days at 5m.",
    );
  const query = new URLSearchParams({ symbol, interval, start, end });
  versions.forEach((v) => query.append("version", v));
  return `/v1/bars?${query}`;
}
export function candleRises(open: string, close: string): boolean {
  return BigInt(close.replace(".", "")) >= BigInt(open.replace(".", ""));
}
export function BarsChart({
  spec,
  results,
}: {
  spec: Data;
  results: Data | null;
}) {
  const [symbol, setSymbol] = useState(spec.symbols[0] as string);
  const [interval, setInterval] = useState("5m");
  const [start, setStart] = useState(spec.start as string);
  const [end, setEnd] = useState(() =>
    new Date(
      Math.min(
        Date.parse(spec.start.slice(0, 10) + "T00:00:00Z") + 86400000,
        Date.parse(spec.end),
      ),
    )
      .toISOString()
      .replace(".000Z", "Z"),
  );
  const [versions, setVersions] = useState(() =>
    selectedVersions()
      .filter(
        (v) =>
          spec.dataset_versions.includes(v.dataset_version_id) &&
          v.symbol === spec.symbols[0] &&
          v.trade_date === spec.start.slice(0, 10),
      )
      .map((v) => v.dataset_version_id)
      .join("\n"),
  );
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState("");
  const r = useResource(path);
  const bars = (r.data?.bars ?? []) as Data[];
  const min = bars.length ? Math.min(...bars.map((b) => Number(b.low))) : 0;
  const max = bars.length ? Math.max(...bars.map((b) => Number(b.high))) : 1;
  const maxVolume = bars.length
    ? Math.max(...bars.map((b) => Number(b.base_volume)))
    : 1;
  const x = (date: string) =>
    ((Date.parse(date) - Date.parse(r.data?.start ?? start)) /
      (Date.parse(r.data?.end ?? end) - Date.parse(r.data?.start ?? start))) *
    1000;
  const y = (value: string) =>
    180 - ((Number(value) - min) / (max - min || 1)) * 160;
  const events = (results?.clusters ?? []) as Data[];
  const load = () => {
    try {
      const ids = versionIDs(versions);
      if (ids.some((v) => !spec.dataset_versions.includes(v)))
        throw new Error(
          "Chart versions must come from this pinned research run.",
        );
      setPath(chartRequest(symbol, interval, start, end, ids));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const selectPinned = async () => {
    try {
      chartRequest(symbol, interval, start, end, ["0".repeat(64)]);
      const query = new URLSearchParams({
        limit: "100",
        symbol,
        start_date: start.slice(0, 10),
        before_date: new Date(Date.parse(end) - 1).toISOString().slice(0, 10),
      });
      query.set(
        "before_date",
        new Date(Date.parse(query.get("before_date") + "T00:00:00Z") + 86400000)
          .toISOString()
          .slice(0, 10),
      );
      const { data } = await request(`/v1/datasets?${query}`);
      if (data.next_cursor)
        throw new Error(
          "Catalog window has more versions than one bounded page. Select exact IDs manually.",
        );
      const rows = (data.items as Data[]).filter((v) =>
        spec.dataset_versions.includes(v.dataset_version_id),
      );
      if (!rows.length)
        throw new Error(
          "No registered pinned versions match this chart window.",
        );
      setVersions(
        rows
          .map((v) => v.dataset_version_id)
          .sort()
          .join("\n"),
      );
      setPath(null);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const shift = (direction: number) => {
    try {
      chartRequest(symbol, interval, start, end, ["0".repeat(64)]);
      const width = Date.parse(end) - Date.parse(start);
      const a = Date.parse(start) + direction * width;
      const b = Date.parse(end) + direction * width;
      if (a < Date.parse(spec.start) || b > Date.parse(spec.end)) return;
      setStart(new Date(a).toISOString().replace(".000Z", "Z"));
      setEnd(new Date(b).toISOString().replace(".000Z", "Z"));
      setPath(null);
      setVersions(
        selectedVersions()
          .filter(
            (v) =>
              spec.dataset_versions.includes(v.dataset_version_id) &&
              v.symbol === symbol &&
              v.trade_date >= new Date(a).toISOString().slice(0, 10) &&
              v.trade_date <= new Date(b - 1).toISOString().slice(0, 10),
          )
          .map((v) => v.dataset_version_id)
          .join("\n"),
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="panel">
      <div className="toolbar">
        <h2>Price and base volume</h2>
        {r.cache && <Tag value={`cache ${r.cache}`} />}
      </div>
      <p className="muted">
        Explicit bounded window · missing buckets stay empty · chart coordinates
        are approximate; the table preserves exact values.
      </p>
      <div className="form-grid">
        <label>
          Chart asset
          <select
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value);
              setPath(null);
              setVersions("");
            }}
          >
            {spec.symbols.map((s: string) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Chart interval
          <select
            value={interval}
            onChange={(e) => {
              setInterval(e.target.value);
              setPath(null);
            }}
          >
            <option value="1m">1 minute</option>
            <option value="5m">5 minutes</option>
          </select>
        </label>
        <label>
          Chart start (UTC)
          <input
            value={start}
            onChange={(e) => {
              setStart(e.target.value);
              setPath(null);
            }}
          />
        </label>
        <label>
          Chart end (UTC, exclusive)
          <input
            value={end}
            onChange={(e) => {
              setEnd(e.target.value);
              setPath(null);
            }}
          />
        </label>
        <label className="wide">
          Chart dataset version IDs
          <textarea
            rows={2}
            value={versions}
            onChange={(e) => {
              setVersions(e.target.value);
              setPath(null);
            }}
          />
          <small>
            Exactly the selected asset's versions for touched UTC days. No
            implicit selection or month-wide chart fetch.
          </small>
        </label>
      </div>
      <div className="actions">
        <button className="secondary" onClick={() => void selectPinned()}>
          Use pinned versions for window
        </button>
        <button onClick={load} disabled={r.busy}>
          Load chart window
        </button>
        <button className="secondary" onClick={() => shift(-1)}>
          Previous window
        </button>
        <button className="secondary" onClick={() => shift(1)}>
          Next window
        </button>
      </div>
      <ErrorBox>{error || r.error}</ErrorBox>
      {r.data && (
        <>
          <p>
            {r.data.returned_buckets} observed / {r.data.expected_buckets}{" "}
            expected · {r.data.empty_buckets} empty buckets
          </p>
          <svg
            role="img"
            aria-label={`${symbol} price candles and base volume; gaps are empty`}
            viewBox="0 0 1000 270"
            className="chart"
          >
            {events
              .filter(
                (v) =>
                  Date.parse(v.start) < Date.parse(end) &&
                  Date.parse(v.end) > Date.parse(start),
              )
              .map((v, i) => (
                <rect
                  key={`event${i}`}
                  x={Math.max(0, x(v.start))}
                  y={10}
                  width={Math.min(1000, x(v.end)) - Math.max(0, x(v.start))}
                  height={250}
                  fill="#d5b956"
                  opacity="0.2"
                >
                  <title>
                    Cluster {v.start} to {v.end}
                  </title>
                </rect>
              ))}
            {bars.map((b) => (
              <g key={b.start}>
                <title>{`${b.start}\nOpen ${b.open}\nHigh ${b.high}\nLow ${b.low}\nClose ${b.close}\nBase volume ${b.base_volume}\nTrades ${b.trade_count}`}</title>
                <line
                  x1={x(b.start) + 1}
                  x2={x(b.start) + 1}
                  y1={y(b.high)}
                  y2={y(b.low)}
                  stroke={candleRises(b.open, b.close) ? "#18746a" : "#bd6457"}
                />
                <rect
                  x={x(b.start)}
                  y={Math.min(y(b.open), y(b.close))}
                  width={Math.max(
                    1,
                    900 / Number(r.data?.expected_buckets ?? 1),
                  )}
                  height={Math.max(1, Math.abs(y(b.close) - y(b.open)))}
                  fill={candleRises(b.open, b.close) ? "#18746a" : "#bd6457"}
                />
                <rect
                  x={x(b.start)}
                  y={260 - (Number(b.base_volume) / (maxVolume || 1)) * 55}
                  width={Math.max(
                    1,
                    900 / Number(r.data?.expected_buckets ?? 1),
                  )}
                  height={(Number(b.base_volume) / (maxVolume || 1)) * 55}
                  fill="#7ba89b"
                />
              </g>
            ))}
          </svg>
          <details>
            <summary>Exact chart values and units</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {[
                      "UTC start",
                      "Open / USDT",
                      "High",
                      "Low",
                      "Close",
                      "Base volume",
                      "Quote volume / USDT",
                      "Trades",
                      "VWAP / USDT",
                    ].map((v) => (
                      <th key={v}>{v}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {bars.map((b) => (
                    <tr key={b.start}>
                      {[
                        "start",
                        "open",
                        "high",
                        "low",
                        "close",
                        "base_volume",
                        "quote_volume",
                        "trade_count",
                        "vwap",
                      ].map((k) => (
                        <td className="exact" key={k}>
                          {b[k]}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
