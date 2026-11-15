import { Fragment, useState, type FormEvent } from "react";
import type { Data } from "../client";
import { ErrorBox, PageTitle, Provenance, Tag, keyLabel } from "../components";
import { minuteLabel, ShortId, stamp, WorkerHint } from "../ui";
import { mutate, type Dataset, type Instrument } from "./api";
import { errorText, useAction, useV2 } from "./hooks";
import { isFlatRecord, isRecord, recordColumns, utc } from "./state";
import { Memo } from "./Memo";
import { ExecutionHistory, ExecutionHost, ExecutionWorker } from "./Execution";
import {
  Facts,
  Field,
  InstrumentPill,
  Pager,
  PinTable,
  SectionHead,
  seriesOf,
  symbolOf,
} from "./parts";

const TITLES: Record<string, string> = {
  market_profile: "Market profile",
  cross_asset: "Cross-asset comparison",
  volatility_cluster: "Volatility clusters",
};
const NUMBER = /^-?\d+(\.\d+)?$/;

type Instruments = Record<string, Instrument>;

function RecordTable({
  items,
  names,
  instruments,
}: {
  items: Record<string, unknown>[];
  names?: string[];
  instruments?: Instruments;
}) {
  const columns = recordColumns(items) ?? [];
  const ids = Object.keys(instruments ?? {});
  // A column is right-aligned when every value it holds is a number.
  const numeric = new Set(
    columns.filter((key) => {
      const cells = items
        .map((item) => item[key])
        .filter((cell) => cell !== null && cell !== undefined);
      return cells.length > 0 && cells.every((c) => NUMBER.test(String(c)));
    }),
  );
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {names && (
              <th>
                <span className="sr-only">Name</span>
              </th>
            )}
            {columns.map((key) => (
              <th key={key} className={numeric.has(key) ? "num" : undefined}>
                {keyLabel(key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr key={i}>
              {names && (
                <td>
                  {instruments?.[names[i]] ? (
                    <InstrumentPill
                      small
                      id={names[i]}
                      instrument={instruments[names[i]]}
                      series={seriesOf(ids, names[i])}
                    />
                  ) : (
                    keyLabel(names[i])
                  )}
                </td>
              )}
              {columns.map((key) => {
                const cell = item[key];
                return (
                  <td
                    key={key}
                    className={numeric.has(key) ? "num" : undefined}
                  >
                    {cell === null || cell === undefined ? (
                      <span className="muted">null</span>
                    ) : (
                      String(cell)
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NumericalData({
  value,
  name = "Numerical value",
  instruments,
}: {
  value: any;
  name?: string;
  instruments?: Instruments;
}) {
  const [page, setPage] = useState(0);
  if (Array.isArray(value)) {
    const pages = Math.max(1, Math.ceil(value.length / 50));
    const shown = value.slice(page * 50, page * 50 + 50);
    const range = value.length
      ? `${page * 50 + 1}–${page * 50 + shown.length} of ${value.length}`
      : "0 of 0";
    return (
      <section className="run-array">
        <div className="array-head">
          <span>{keyLabel(name)}</span>
          {pages > 1 ? (
            <Pager
              page={page}
              pages={pages}
              onPage={setPage}
              label={name.replaceAll("_", " ")}
              text={range}
            />
          ) : (
            <span className="muted">{range}</span>
          )}
        </div>
        {shown.length > 0 && recordColumns(shown) && shown.every(isRecord) ? (
          <RecordTable items={shown} instruments={instruments} />
        ) : (
          shown.map((item, i) => (
            <NumericalData
              key={page * 50 + i}
              value={item}
              name={`${name}_${page * 50 + i + 1}`}
              instruments={instruments}
            />
          ))
        )}
      </section>
    );
  }
  if (isRecord(value)) {
    // Entries that are flat records of one shape (a metric's value, reason
    // and observation count, say) read as rows of a table; the rest stay in
    // the key/value list.
    const entries = Object.entries(value);
    const shape = (entry: unknown) =>
      isFlatRecord(entry) ? Object.keys(entry).join("\n") : null;
    const shapes = entries.map(([, entry]) => shape(entry));
    const common = shapes.find(
      (s) => s !== null && shapes.filter((v) => v === s).length >= 2,
    );
    const rows = entries.filter((_, i) => common && shapes[i] === common);
    const rest = entries.filter((_, i) => !common || shapes[i] !== common);
    const table = rows.length > 0 && (
      <RecordTable
        items={rows.map(([, entry]) => entry as Record<string, unknown>)}
        names={rows.map(([key]) => key)}
        instruments={instruments}
      />
    );
    if (!rest.length) return table;
    const ids = Object.keys(instruments ?? {});
    const list = (
      <dl className="kv">
        {rest.map(([key, entry]) => (
          <div key={key}>
            <dt>
              {instruments?.[key] ? (
                <InstrumentPill
                  small
                  id={key}
                  instrument={instruments[key]}
                  series={seriesOf(ids, key)}
                />
              ) : (
                keyLabel(key)
              )}
            </dt>
            <dd>
              <NumericalData
                value={entry}
                name={key}
                instruments={instruments}
              />
            </dd>
          </div>
        ))}
      </dl>
    );
    if (!table) return list;
    return (
      <div className="run-array">
        {shapes[0] === common ? table : list}
        {shapes[0] === common ? list : table}
      </div>
    );
  }
  return value === null ? (
    <span className="null-value">Unavailable (null)</span>
  ) : (
    <span className="exact">{String(value)}</span>
  );
}

export function Run({
  id,
  memoAvailable,
}: {
  id: string;
  memoAvailable: boolean;
}) {
  const status = useV2(`/v2/research/runs/${id}`, true);
  const summary = useV2(
    status.data?.numerical_available ? `/v2/research/runs/${id}/summary` : null,
  );
  const [wantResults, setWantResults] = useState(false);
  const results = useV2(
    status.data?.numerical_available && wantResults
      ? `/v2/research/runs/${id}/results`
      : null,
  );
  const action = useAction();
  const info = status.data;
  const instruments: Record<string, Instrument> =
    info?.fingerprint?.instruments ?? {};
  const ids = Object.keys(instruments);
  const datasets = (info?.fingerprint?.datasets ?? []) as Dataset[];
  const terminal = ["succeeded", "failed", "cancelled"].includes(info?.state);
  return (
    <>
      <PageTitle
        title={
          info ? (TITLES[info.spec.workflow] ?? "Research run") : "Research run"
        }
        meta={
          info && (
            <div className="pairs">
              {ids.map((instrumentId, i) => (
                <Fragment key={instrumentId}>
                  {i > 0 && <span className="muted">vs</span>}
                  <InstrumentPill
                    id={instrumentId}
                    instrument={instruments[instrumentId]}
                    series={seriesOf(ids, instrumentId)}
                  />
                </Fragment>
              ))}
              <ShortId value={id} label="research run ID" />
            </div>
          )
        }
      >
        <div className="title-actions">
          {info && <Tag value={info.state} />}
          {info && !terminal && (
            <button
              type="button"
              className="secondary"
              disabled={action.busy || info.cancel_requested}
              onClick={() =>
                void action.run(async () => {
                  await mutate(
                    `research-cancel-${id}-${info.revision}`,
                    `/v2/research/runs/${id}/cancel`,
                    { expected_revision: info.revision },
                  );
                  status.refresh();
                })
              }
            >
              Cancel run
            </button>
          )}
          <button type="button" className="secondary" onClick={status.refresh}>
            Refresh
          </button>
        </div>
      </PageTitle>
      <ErrorBox>{status.error || action.error}</ErrorBox>
      {info && (
        <>
          <Facts
            items={[
              ["History start", stamp(info.spec.history_start)],
              ["Evaluation start", stamp(info.spec.start)],
              ["Evaluation end", stamp(info.spec.end)],
              ["Interval", info.spec.interval],
              ["Attempts", info.attempt_count],
              [
                "Host",
                <ExecutionHost
                  execution={info.execution_status}
                  state={info.state}
                />,
              ],
              [
                "Worker",
                <ExecutionWorker
                  execution={info.execution_status}
                  state={info.state}
                />,
              ],
            ]}
          />
          {info.error_code && <ErrorBox>{info.error_code}</ErrorBox>}
          {["queued", "running", "retry_wait"].includes(info.state) && (
            <WorkerHint
              kind="research_v2"
              id={id}
              running={info.state === "running"}
            />
          )}
          <ExecutionHistory
            execution={info.execution_status}
            state={info.state}
          />
          {info.numerical_available && (
            <>
              <section className="section">
                <SectionHead title="Summary" />
                <ErrorBox>{summary.error}</ErrorBox>
                {summary.data && (
                  <NumericalData
                    value={summary.data}
                    instruments={instruments}
                  />
                )}
              </section>
              <section className="section">
                <SectionHead title="Results">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setWantResults(true)}
                    disabled={results.busy}
                  >
                    Load results
                  </button>
                </SectionHead>
                <ErrorBox>{results.error}</ErrorBox>
                {results.data && (
                  <NumericalData
                    value={results.data}
                    instruments={instruments}
                  />
                )}
              </section>
              <Bars info={info} />
              <Memo id={id} available={memoAvailable} />
            </>
          )}
          <section className="section">
            <SectionHead title="Pinned versions">
              <span className="count muted">
                {datasets.length}{" "}
                {datasets.length === 1 ? "version" : "versions"}
              </span>
            </SectionHead>
            <PinTable
              rows={datasets}
              instruments={new Map(Object.entries(instruments))}
            />
          </section>
          <Provenance
            data={{
              spec: info.spec,
              fingerprint: info.fingerprint,
              attempts: info.attempts,
              revision: info.revision,
            }}
            title="Request and provenance"
          />
        </>
      )}
    </>
  );
}
function Bars({ info }: { info: Data }) {
  const spec = info.spec;
  const [instrument, setInstrument] = useState(spec.instrument_ids[0]);
  const [interval, setInterval] = useState("5m");
  // Deliberately blank: research can exceed chart bounds. The user explicitly
  // chooses the chart window; there is no silently truncated initial chart.
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState("");
  const bars = useV2(path);
  const [page, setPage] = useState(0);
  const rows = bars.data?.bars as Data[] | undefined;
  const choose = (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const minutes = interval === "1m" ? 1 : 5;
      const first = utc(start, minutes),
        before = utc(end, minutes);
      if (
        first >= before ||
        first < Date.parse(spec.history_start) ||
        before > Date.parse(spec.end)
      )
        throw new Error(
          "Choose a window inside the run's history and evaluation range.",
        );
      const buckets = (before - first) / (minutes * 60000);
      if (buckets > 1440)
        throw new Error(
          "At most 1,440 bars. Narrow the window or use 5 minutes.",
        );
      const days =
        Math.floor((before - 1) / 86400000) - Math.floor(first / 86400000) + 1;
      if (days > 5) throw new Error("At most 5 days per chart.");
      const versions = info.fingerprint.datasets.filter(
        (row: Data) =>
          row.instrument_id === instrument &&
          row.trade_date >= new Date(first).toISOString().slice(0, 10) &&
          row.trade_date <= new Date(before - 1).toISOString().slice(0, 10),
      );
      const params = new URLSearchParams({
        instrument_id: instrument,
        interval,
        start,
        end,
      });
      versions.forEach((row: Data) =>
        params.append("version", row.dataset_version_id),
      );
      setPath(`/v2/bars?${params.toString()}`);
      setPage(0);
    } catch (e) {
      setError(errorText(e));
    }
  };
  const units = bars.data?.units;
  const pages = rows ? Math.ceil(rows.length / 100) : 0;
  const columns: [string, string, string | undefined][] = units
    ? [
        ["start", "Start", undefined],
        ["open", "Open", units.price],
        ["high", "High", units.price],
        ["low", "Low", units.price],
        ["close", "Close", units.price],
        ["vwap", "VWAP", units.price],
        ["base_volume", "Base volume", units.base_volume],
        ["quote_volume", "Quote volume", units.quote_volume],
        ["trade_count", "Trades", undefined],
      ]
    : [];
  return (
    <section className="section">
      <SectionHead title="Chart" />
      <form className="controls" onSubmit={choose}>
        <label>
          Instrument
          <select
            aria-label="Instrument"
            value={instrument}
            onChange={(e) => {
              setInstrument(e.target.value);
              setPath(null);
            }}
          >
            {spec.instrument_ids.map((id: string) => (
              <option key={id} value={id}>
                {symbolOf(id)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Interval
          <select
            aria-label="Interval"
            value={interval}
            onChange={(e) => setInterval(e.target.value)}
          >
            <option value="1m">1 minute</option>
            <option value="5m">5 minutes</option>
          </select>
        </label>
        <Field
          title="Start"
          value={start}
          change={setStart}
          placeholder="2025-03-01T00:00:00Z"
        />
        <Field
          title="End"
          value={end}
          change={setEnd}
          placeholder="2025-03-02T00:00:00Z"
        />
        <button type="submit" className="secondary" disabled={bars.busy}>
          Load chart
        </button>
      </form>
      <small className="muted">Up to 1,440 bars across 5 days</small>
      <ErrorBox>{error || bars.error}</ErrorBox>
      {rows && bars.data && units && (
        <>
          <Facts
            items={[
              [
                "Bars",
                `${String(bars.data.returned_buckets)} of ${String(bars.data.expected_buckets)}`,
              ],
              ["Empty", String(bars.data.empty_buckets)],
              ["Price unit", units.price],
              ["Base volume unit", units.base_volume],
            ]}
          />
          <PriceChart
            rows={rows}
            interval={bars.data.interval}
            start={bars.data.start}
            end={bars.data.end}
            unit={units.price}
          />
          <div className="table-wrap">
            <table>
              <caption>Chart bars</caption>
              <thead>
                <tr>
                  {columns.map(([key, title, unit]) => (
                    <th
                      key={key}
                      className={key === "start" ? undefined : "num"}
                    >
                      {title}
                      {unit && <span className="muted"> {unit}</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(page * 100, (page + 1) * 100).map((row) => (
                  <tr key={row.start}>
                    {columns.map(([key]) => (
                      <td
                        key={key}
                        className={key === "start" ? undefined : "num"}
                      >
                        {row[key] === null ? (
                          <span className="muted">null</span>
                        ) : (
                          String(row[key])
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <Pager
              page={page}
              pages={pages}
              onPage={setPage}
              label="bars"
              text={`${page * 100 + 1}–${Math.min(rows.length, (page + 1) * 100)} of ${rows.length}`}
            />
          )}
          <Provenance
            data={{ ...bars.data, bars: undefined }}
            title="Chart provenance"
          />
        </>
      )}
    </section>
  );
}
export function chartSegments(
  rows: Data[],
  interval: string,
  start: string,
  end: string,
) {
  const points = rows
    .filter(
      (row) =>
        row.close !== null && row.close !== undefined && row.close !== "",
    )
    .map((row) => ({ x: Date.parse(row.start), y: Number(row.close) }))
    .filter((row) => Number.isFinite(row.x) && Number.isFinite(row.y));
  if (!points.length) return [];
  const min = Math.min(...points.map((p) => p.y)),
    max = Math.max(...points.map((p) => p.y));
  const first = Date.parse(start),
    before = Date.parse(end);
  const step = interval === "1m" ? 60000 : 300000;
  const paths: string[] = [];
  let prior = Number.NaN;
  for (const point of points) {
    const value = `${30 + ((point.x - first) / Math.max(step, before - first)) * 940},${210 - ((point.y - min) / (max - min || 1)) * 180}`;
    if (point.x - prior !== step) paths.push(`M${value}`);
    else paths[paths.length - 1] += ` L${value}`;
    prior = point.x;
  }
  return paths;
}
function PriceChart({
  rows,
  interval,
  start,
  end,
  unit,
}: {
  rows: Data[];
  interval: string;
  start: string;
  end: string;
  unit: string;
}) {
  const segments = chartSegments(rows, interval, start, end);
  // The axis labels print the exact close strings of the lowest and highest bars.
  const closes = rows.filter(
    (row) => row.close !== null && Number.isFinite(Number(row.close)),
  );
  const low = closes.reduce<Data | null>(
    (best, row) =>
      !best || Number(row.close) < Number(best.close) ? row : best,
    null,
  );
  const high = closes.reduce<Data | null>(
    (best, row) =>
      !best || Number(row.close) > Number(best.close) ? row : best,
    null,
  );
  return (
    <section className="chart-panel graphite" aria-label="Close price chart">
      <div className="chart-legend">
        <span>
          <i style={{ background: "var(--gr-5)" }} />
          Close
        </span>
        <span className="unit">{unit}</span>
      </div>
      {segments.length ? (
        <svg
          viewBox="0 0 1000 240"
          role="img"
          aria-label={`Close price in ${unit}; gaps are disconnected; exact values in table below`}
          className="chart-svg"
        >
          <path d="M30 30V210H970" className="chart-axis" />
          {segments.map((segment, i) => (
            <path key={i} d={segment} className="chart-line" />
          ))}
          {high && (
            <text x={36} y={22} className="chart-label">
              {String(high.close)}
            </text>
          )}
          {low && (
            <text x={36} y={224} className="chart-label">
              {String(low.close)}
            </text>
          )}
          <text x={30} y={238} className="chart-label">
            {minuteLabel(start)}
          </text>
          <text x={970} y={238} textAnchor="end" className="chart-label">
            {minuteLabel(end)}
          </text>
        </svg>
      ) : (
        <p className="chart-empty">No bars in this window.</p>
      )}
    </section>
  );
}
