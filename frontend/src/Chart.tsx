import { Fragment, useState } from "react";
import { request, selectedVersions, versionIDs, type Data } from "./client";
import { useResource } from "./hooks";
import { ErrorBox } from "./components";
import {
  dayLabel,
  Icon,
  minuteLabel,
  Pair,
  pairText,
  SERIES,
  Spinner,
  splitPair,
  trimmed,
} from "./ui";
const UP = "#3fc07a";
const DOWN = "#ef5b6b";
const WARN = "#e0b04a";
const GRAPHITE = ["#1c1c1e", "#38383b", "#65656b", "#a5a5ac", "#f5f5f5"];
const DAY = 86_400_000;
const STEP = 300_000;
const iso = (t: number) => new Date(t).toISOString().replace(".000Z", "Z");
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
function niceTicks(min: number, max: number, count = 4) {
  const span = max - min || Math.abs(max) || 1;
  const raw = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / magnitude;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * magnitude;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step)
    ticks.push(Number(v.toPrecision(12)));
  return { ticks, step };
}
const tickText = (value: number, step: number) =>
  step >= 1
    ? Math.round(value).toLocaleString("en-US")
    : value.toFixed(Math.min(8, Math.max(0, -Math.floor(Math.log10(step)))));
/** Five-day pages of the evaluation window, aligned to UTC days so no page touches more than five daily versions. */
function closeWindow(spec: Data, page: number) {
  const start = Date.parse(spec.start);
  const end = Date.parse(spec.end);
  const base = Math.floor(start / DAY) * DAY;
  return {
    start: iso(page === 0 ? start : base + page * 5 * DAY),
    end: iso(Math.min(end, base + (page + 1) * 5 * DAY)),
    pages: Math.max(1, Math.ceil((end - base) / (5 * DAY))),
  };
}
/** Close price over the evaluation window. Bars are read only when asked, one bounded window per asset. */
export function CloseChart({
  spec,
  rows,
}: {
  spec: Data;
  rows: Data[] | null;
}) {
  const symbols = spec.symbols as string[];
  const cross = symbols.length > 1;
  const [page, setPage] = useState(0);
  const [paths, setPaths] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const win = closeWindow(spec, page);
  const versionsFor = (sym: string, w: { start: string; end: string }) => {
    const first = w.start.slice(0, 10);
    const last = iso(Date.parse(w.end) - 1).slice(0, 10);
    return (rows ?? [])
      .filter(
        (v) =>
          v.symbol === sym && v.trade_date >= first && v.trade_date <= last,
      )
      .map((v) => String(v.dataset_version_id))
      .sort();
  };
  const load = (next: number) => {
    try {
      if (!rows) throw new Error("Pinned version details are still loading.");
      const w = closeWindow(spec, next);
      setPaths(
        symbols.map((sym) => {
          const ids = versionsFor(sym, w);
          if (!ids.length)
            throw new Error(
              `No pinned ${pairText(sym)} versions cover this window.`,
            );
          return chartRequest(sym, "5m", w.start, w.end, ids);
        }),
      );
      setPage(next);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const first = useResource(paths?.[0] ?? null);
  // One asset at a time, so this chart never holds both analytical read slots.
  const second = useResource(first.data ? (paths?.[1] ?? null) : null);
  const reads = [first, second].slice(0, symbols.length);
  const loaded = paths !== null && reads.every((r) => r.data);
  const expected = (Date.parse(win.end) - Date.parse(win.start)) / STEP;
  const pinnedCount = symbols.reduce(
    (n, sym) => n + versionsFor(sym, win).length,
    0,
  );
  const range = `${minuteLabel(win.start)} to ${minuteLabel(iso(Date.parse(win.end) - STEP))} UTC`;
  const W = 1000;
  const H = 240;
  const plot = W - 72;
  const ws = Date.parse(win.start);
  const we = Date.parse(win.end);
  const series = loaded
    ? reads.map((r) => {
        const bars = (r.data!.bars ?? []) as Data[];
        const base = Number(bars[0]?.close);
        return bars.map((b) => ({
          t: Date.parse(b.start),
          close: String(b.close),
          v: cross ? Number(b.close) / base - 1 : Number(b.close),
        }));
      })
    : [];
  const values = series.flat().map((p) => p.v);
  const lo = values.length ? Math.min(...values) : 0;
  const hi = values.length ? Math.max(...values) : 1;
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.06;
  const { ticks, step } = niceTicks(lo - pad, hi + pad);
  const y0 = Math.min(lo - pad, ticks[0] ?? lo);
  const y1 = Math.max(hi + pad, ticks[ticks.length - 1] ?? hi);
  const x = (t: number) => ((t - ws) / (we - ws)) * plot;
  const y = (v: number) => 14 + (1 - (v - y0) / (y1 - y0 || 1)) * (H - 44);
  const line = (points: { t: number; v: number }[]) =>
    points
      .map(
        (p, i) =>
          `${i && p.t - points[i - 1].t === STEP ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p.v).toFixed(1)}`,
      )
      .join("");
  const midnights: number[] = [];
  for (let t = Math.ceil(ws / DAY) * DAY; t < we; t += DAY) midnights.push(t);
  const only = series[0] ?? [];
  const high = only.reduce((m, p, i) => (p.v > only[m].v ? i : m), 0);
  const low = only.reduce((m, p, i) => (p.v < only[m].v ? i : m), 0);
  return (
    <section className="chart-panel graphite" aria-labelledby="close-title">
      <div className="toolbar">
        <div>
          <h2 id="close-title">
            {cross ? "Close change from window start" : "Close price"}
          </h2>
          <p className="meta">
            {expected} five-minute bars{cross ? " per asset" : ""}, {range}
          </p>
        </div>
        {cross && (
          <div className="pairs">
            {symbols.map((sym, i) => (
              <Pair key={sym} symbol={sym} series={i} small />
            ))}
          </div>
        )}
      </div>
      <ErrorBox>{error || reads.map((r) => r.error).find(Boolean)}</ErrorBox>
      {!paths && (
        <div className="chart-empty">
          <span>
            {rows
              ? `Reads ${expected} five-minute bars${cross ? " per asset" : ""} from ${pinnedCount} pinned ${pinnedCount === 1 ? "version" : "versions"}.`
              : "Looking up pinned versions…"}
          </span>
          <button disabled={!rows} onClick={() => load(page)}>
            {cross ? "Load closes" : "Load close price"}
          </button>
        </div>
      )}
      {paths && !loaded && !reads.some((r) => r.error) && (
        <p className="chart-empty" role="status">
          <span>
            <Spinner /> Reading bars
          </span>
        </p>
      )}
      {loaded && (
        <>
          <svg
            role="img"
            aria-label={
              cross
                ? `Close change from window start for ${symbols.map(pairText).join(" and ")}, ${range}`
                : `${pairText(symbols[0])} close price, ${range}`
            }
            viewBox={`0 0 ${W} ${H}`}
            className="chart"
          >
            {ticks.map((v) => (
              <Fragment key={v}>
                <line
                  x1={0}
                  x2={plot}
                  y1={y(v)}
                  y2={y(v)}
                  stroke={GRAPHITE[1]}
                  strokeWidth={1}
                />
                <text
                  x={plot + 10}
                  y={y(v) + 4}
                  fill={GRAPHITE[2]}
                  fontSize={11}
                >
                  {tickText(v, step)}
                </text>
              </Fragment>
            ))}
            {midnights.map((t) => (
              <Fragment key={t}>
                <line
                  x1={x(t)}
                  x2={x(t)}
                  y1={H - 30}
                  y2={H - 24}
                  stroke={GRAPHITE[2]}
                />
                <text x={x(t) + 4} y={H - 8} fill={GRAPHITE[2]} fontSize={11}>
                  {dayLabel(iso(t))}
                </text>
              </Fragment>
            ))}
            {series.map((points, i) => (
              <path
                key={symbols[i]}
                d={line(points)}
                fill="none"
                stroke={cross ? SERIES[i] : GRAPHITE[4]}
                strokeWidth={1.5}
                strokeLinejoin="round"
                pathLength={1}
                className="draw"
              />
            ))}
            {!cross && only.length > 1 && (
              <>
                {[high, low].map((i, k) => (
                  <Fragment key={k}>
                    <circle
                      cx={x(only[i].t)}
                      cy={y(only[i].v)}
                      r={3}
                      fill={GRAPHITE[4]}
                    />
                    <text
                      x={Math.min(plot - 4, Math.max(4, x(only[i].t)))}
                      y={y(only[i].v) + (k ? 18 : -9)}
                      textAnchor={
                        x(only[i].t) > plot * 0.85
                          ? "end"
                          : x(only[i].t) < plot * 0.15
                            ? "start"
                            : "middle"
                      }
                      fill={GRAPHITE[3]}
                      fontSize={11}
                    >
                      {trimmed(only[i].close)}
                    </text>
                  </Fragment>
                ))}
              </>
            )}
            {cross &&
              series.map((points, i) => {
                const end = points[points.length - 1];
                return end ? (
                  <text
                    key={symbols[i]}
                    x={x(end.t) + 6}
                    y={y(end.v) + 4}
                    fill={SERIES[i]}
                    fontSize={11}
                  >
                    {splitPair(symbols[i])[0]}
                  </text>
                ) : null;
              })}
          </svg>
          <div className="chart-foot">
            {series.map((points, i) => (
              <span key={symbols[i]}>
                {cross ? `${splitPair(symbols[i])[0]} ` : ""}first close{" "}
                <b>{trimmed(points[0]?.close ?? "")}</b> last close{" "}
                <b className="last">
                  {trimmed(points[points.length - 1]?.close ?? "")}
                </b>
              </span>
            ))}
            <span>
              {reads[0].data!.returned_buckets} of{" "}
              {reads[0].data!.expected_buckets} buckets observed
            </span>
          </div>
        </>
      )}
      {win.pages > 1 && (
        <div className="actions">
          <button
            className="secondary"
            disabled={page === 0}
            onClick={() => (paths ? load(page - 1) : setPage(page - 1))}
          >
            <Icon name="left" size={14} />
            Previous 5 days
          </button>
          <button
            className="secondary"
            disabled={page >= win.pages - 1}
            onClick={() => (paths ? load(page + 1) : setPage(page + 1))}
          >
            Next 5 days
            <Icon name="right" size={14} />
          </button>
        </div>
      )}
    </section>
  );
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
  const [hover, setHover] = useState<number | null>(null);
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
  const focus = bars[hover ?? bars.length - 1] ?? bars[bars.length - 1];
  const base = splitPair(String(r.data?.symbol ?? symbol))[0];
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
  const width = Math.max(1, 900 / Number(r.data?.expected_buckets ?? 1));
  return (
    <section className="chart-panel" aria-labelledby="bars-title">
      <div className="toolbar">
        <h2 id="bars-title">Price and base volume</h2>
        <span className="coverage">
          Gaps stay empty. Exact values are in the table under the chart.
        </span>
      </div>
      <div className="chart-controls">
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
              <option key={s} value={s}>
                {pairText(s)}
              </option>
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
            This asset's versions for every UTC day the window touches.
          </small>
        </label>
      </div>
      <div className="actions">
        <button className="secondary" onClick={() => void selectPinned()}>
          Use pinned versions for window
        </button>
        <button className="secondary" onClick={load} disabled={r.busy}>
          Load chart window
        </button>
        <button className="secondary" onClick={() => shift(-1)}>
          <Icon name="left" size={14} />
          Previous window
        </button>
        <button className="secondary" onClick={() => shift(1)}>
          Next window
          <Icon name="right" size={14} />
        </button>
      </div>
      <ErrorBox>{error || r.error}</ErrorBox>
      {r.data && (
        <>
          <div className="toolbar">
            <span className="coverage">
              {r.data.returned_buckets} of {r.data.expected_buckets} buckets
              observed, {r.data.empty_buckets} empty
            </span>
            {r.cache === "hit" && (
              <span className="coverage">Served from cache</span>
            )}
          </div>
          {focus && (
            <div className="readout">
              <span className="when">{minuteLabel(focus.start)}</span>
              <span>
                O <b>{trimmed(focus.open)}</b>
              </span>
              <span>
                H <b>{trimmed(focus.high)}</b>
              </span>
              <span>
                L <b>{trimmed(focus.low)}</b>
              </span>
              <span>
                C <b>{trimmed(focus.close)}</b>
              </span>
              <span>
                V <b>{trimmed(focus.base_volume)}</b> {base}
              </span>
              <span>
                trades <b>{focus.trade_count}</b>
              </span>
            </div>
          )}
          <svg
            role="img"
            aria-label={`${symbol} price candles and base volume; gaps are empty`}
            viewBox="0 0 1000 270"
            className="chart"
            onMouseLeave={() => setHover(null)}
          >
            <line x1={0} x2={1000} y1={197} y2={197} stroke="#1d1f24" />
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
                  fill={WARN}
                  opacity="0.14"
                >
                  <title>
                    Cluster {v.start} to {v.end}
                  </title>
                </rect>
              ))}
            {bars.map((b, i) => {
              const color = candleRises(b.open, b.close) ? UP : DOWN;
              return (
                <g key={b.start} onMouseEnter={() => setHover(i)}>
                  <title>{`${b.start}\nOpen ${b.open}\nHigh ${b.high}\nLow ${b.low}\nClose ${b.close}\nBase volume ${b.base_volume}\nTrades ${b.trade_count}`}</title>
                  <line
                    x1={x(b.start) + width / 2}
                    x2={x(b.start) + width / 2}
                    y1={y(b.high)}
                    y2={y(b.low)}
                    stroke={color}
                  />
                  <rect
                    x={x(b.start)}
                    y={Math.min(y(b.open), y(b.close))}
                    width={width}
                    height={Math.max(1, Math.abs(y(b.close) - y(b.open)))}
                    fill={color}
                  />
                  <rect
                    x={x(b.start)}
                    y={260 - (Number(b.base_volume) / (maxVolume || 1)) * 55}
                    width={width}
                    height={(Number(b.base_volume) / (maxVolume || 1)) * 55}
                    fill={color}
                    opacity={hover === i ? 0.9 : 0.45}
                  />
                </g>
              );
            })}
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
