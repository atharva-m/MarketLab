import { Fragment, useState } from "react";
import { request, type Data } from "./client";
import { useResource } from "./hooks";
import {
  active,
  DataView,
  ErrorBox,
  label,
  PageTitle,
  Provenance,
  Refresh,
  Tag,
} from "./components";
import { BarsChart, CloseChart } from "./Chart";
import { useCatalogRows } from "./Catalog";
import {
  CopyButton,
  dayLabel,
  dayRange,
  duration,
  Exact,
  Figure,
  minuteLabel,
  Pair,
  ShortId,
  splitPair,
  stamp,
  trimmed,
  venueName,
  WorkerHint,
} from "./ui";
const TITLES: Record<string, string> = {
  market_profile: "Market profile",
  cross_asset: "Cross-asset comparison",
  volatility_cluster: "Volatility clusters",
};
const DAY = 86_400_000;
const iso = (t: number) => new Date(t).toISOString().replace(".000Z", "Z");
const lastDay = (end: string) => iso(Date.parse(end) - 1).slice(0, 10);
const nextDay = (date: string) =>
  iso(Date.parse(`${date}T00:00:00Z`) + DAY).slice(0, 10);
type Stat = {
  value: string | null;
  reason: string | null;
  observation_count: number;
};
const isStat = (v: unknown): v is Stat =>
  typeof v === "object" &&
  v !== null &&
  "value" in v &&
  "observation_count" in v;
const sign = (v: unknown) =>
  typeof v !== "string"
    ? undefined
    : v.startsWith("-")
      ? "down"
      : /[1-9]/.test(v)
        ? "up"
        : undefined;
const NULL = <span className="null-value">Unavailable (null)</span>;
function stat(s: Stat | undefined, note?: string) {
  if (!s) return { value: NULL, note: undefined };
  if (s.value === null)
    return {
      value: NULL,
      note: `${label(s.reason ?? "no reason given")}, ${s.observation_count} observations`,
    };
  return {
    value: <Exact value={s.value} digits={6} />,
    note: note ?? `${s.observation_count} observations`,
  };
}
function WindowTrack({ spec }: { spec: Data }) {
  const history = Date.parse(spec.history_start);
  const start = Date.parse(spec.start);
  const end = Date.parse(spec.end);
  const total = end - history || 1;
  const midnights: number[] = [];
  for (let t = Math.ceil(history / DAY) * DAY; t <= end; t += DAY)
    midnights.push(t);
  const every = Math.max(1, Math.ceil(midnights.length / 7));
  const versions = (spec.dataset_versions as string[]).length;
  const symbols = spec.symbols as string[];
  return (
    <section className="window" aria-label="Run window">
      <div className="track-cell">
        <div className="head">
          <span>Window, UTC</span>
          <span>
            <span className="legend-item">
              <i className="swatch" style={{ background: "var(--ti-3)" }} />
              warm-up {duration(start - history)}
            </span>
            <span className="legend-item">
              <i className="swatch" style={{ background: "var(--ti-5)" }} />
              evaluated {duration(end - start)}
            </span>
          </span>
        </div>
        <div className="track">
          <span
            className="warm"
            style={{ flex: `0 0 ${((start - history) / total) * 100}%` }}
            title={`Warm-up ${spec.history_start} to ${spec.start}`}
          />
          <span
            className="eval"
            title={`Evaluated ${spec.start} to ${spec.end}, end exclusive`}
          />
        </div>
        <div className="ticks" aria-hidden="true">
          {midnights
            .filter((_, i) => i % every === 0)
            .map((t) => {
              const at = (t - history) / total;
              return (
                <span
                  key={t}
                  style={{
                    left: `${at * 100}%`,
                    transform:
                      at > 0.96
                        ? "translateX(-100%)"
                        : at > 0.03
                          ? "translateX(-50%)"
                          : undefined,
                  }}
                >
                  {dayLabel(iso(t))}
                </span>
              );
            })}
        </div>
        <p className="sr-only">
          Warm-up from {stamp(spec.history_start)}, evaluation from{" "}
          {stamp(spec.start)} until {stamp(spec.end)}, end exclusive.
        </p>
      </div>
      <div className="fact">
        <div className="k">Bars</div>
        <div className="v">
          {spec.interval === "5m" ? "5 minutes" : spec.interval}
        </div>
      </div>
      <div className="fact">
        <div className="k">Pinned data</div>
        <div className="v">
          {versions} {versions === 1 ? "version" : "versions"}
        </div>
        <div className="s">
          {dayRange(spec.history_start, lastDay(spec.end))}
          {symbols.length > 1 ? ", both assets" : ""}
        </div>
      </div>
    </section>
  );
}
const PLACEHOLDER = (
  <span className="placeholder">
    <span className="sr-only">Pending</span>
  </span>
);
function Figures({ spec, summary }: { spec: Data; summary: Data | null }) {
  const symbols = spec.symbols as string[];
  if (spec.workflow === "cross_asset") {
    const ca = summary?.cross_asset;
    if (!summary)
      return (
        <div className="figures">
          <Figure
            lead
            label="Return correlation"
            unit="Pearson"
            value={PLACEHOLDER}
          />
          <Figure
            label="Close change difference"
            unit="ratio"
            value={PLACEHOLDER}
          />
          <Figure label="Common bars" value={PLACEHOLDER} />
        </div>
      );
    if (!ca) return null;
    const expected = summary.profiles?.[symbols[0]]?.coverage?.expected;
    const [a, b] = symbols.map((s) => splitPair(s)[0]);
    const corr = stat(
      ca.correlation,
      `${ca.aligned_return_count} aligned five-minute log returns`,
    );
    const diff = stat(
      ca.close_change_difference,
      `${a} minus ${b}, common endpoints`,
    );
    return (
      <div className="figures">
        {ca.correlation && (
          <Figure lead label="Return correlation" unit="Pearson" {...corr} />
        )}
        {ca.close_change_difference && (
          <Figure
            label="Close change difference"
            unit="ratio"
            tone={sign(ca.close_change_difference.value)}
            {...diff}
          />
        )}
        <Figure
          label="Common bars"
          value={
            expected === undefined
              ? ca.common_bar_count
              : `${ca.common_bar_count} / ${expected}`
          }
          note={
            expected === undefined
              ? undefined
              : `${Number(expected) - Number(ca.common_bar_count)} missing on either asset`
          }
        />
      </div>
    );
  }
  if (!summary)
    return (
      <div className="figures">
        {[
          ["VWAP", "USDT"],
          ["Close change", "ratio"],
          ["Drawdown", "ratio"],
          ["Sharpe proxy", "unannualized"],
          ["Trades", ""],
          ["Coverage", "bars"],
        ].map(([name, unit], i) => (
          <Figure
            key={name}
            lead={i === 0}
            label={name}
            unit={unit}
            value={PLACEHOLDER}
          />
        ))}
      </div>
    );
  const sym = symbols[0];
  const p = summary.profiles?.[sym];
  if (!p) return null;
  const units = summary.units ?? {};
  const counts = summary.cluster_counts;
  const coverage = p.coverage ?? {};
  const warm = summary.history?.[sym]?.observed_bars;
  return (
    <div className="figures">
      <Figure lead label="VWAP" unit={units.price} {...stat(p.vwap)} />
      <Figure
        label="Close change"
        unit="ratio"
        tone={sign(p.close_change?.value)}
        {...stat(p.close_change)}
      />
      <Figure
        label="Drawdown"
        unit="ratio"
        tone={sign(p.drawdown?.value)}
        {...stat(p.drawdown)}
      />
      {counts ? (
        <Figure
          label="Clusters"
          value={counts.clusters}
          note={`${counts.qualifying} qualifying bars, ${counts.ineligible} ineligible`}
        />
      ) : (
        <Figure
          label="Sharpe proxy"
          unit="unannualized"
          {...stat(p.sharpe, "mean / std dev of 5-minute returns")}
        />
      )}
      <Figure
        label="Trades"
        value={<span className="exact">{p.trade_count}</span>}
        note={
          <>
            base volume {trimmed(p.base_volume)}{" "}
            {units.base_volume?.[sym] ?? ""}
          </>
        }
      />
      <Figure
        label="Coverage"
        unit="bars"
        value={`${coverage.observed} / ${coverage.expected}`}
        note={`${coverage.missing} missing${warm !== undefined ? `, ${warm} warm-up bars` : ""}`}
      />
    </div>
  );
}
const PROFILE: [string, string, string][] = [
  ["First open", "first_open", "price"],
  ["High", "high", "price"],
  ["Low", "low", "price"],
  ["Last close", "last_close", "price"],
  ["VWAP", "vwap", "price"],
  ["Close change", "close_change", "ratio"],
  ["Return mean", "return_mean", "ratio"],
  ["Return std dev", "return_stddev", "ratio"],
  ["Sharpe proxy, unannualized", "sharpe", "ratio"],
  ["Drawdown", "drawdown", "ratio"],
  ["Base volume", "base_volume", "base"],
  ["Quote volume", "quote_volume", "quote"],
  ["Trades", "trade_count", "count"],
  ["Undefined returns", "undefined_returns", "count"],
  ["Undefined volume windows", "undefined_volume_windows", "count"],
];
const KNOWN = new Set([
  "schema",
  "definition",
  "workflow",
  "start",
  "end",
  "history_start",
  "history",
  "interval",
  "units",
  "profiles",
  "cross_asset",
  "clusters",
  "cluster_counts",
]);
function Value({ value, unit }: { value: unknown; unit?: string }) {
  if (isStat(value) && value.value === null)
    return (
      <>
        {NULL} <span className="muted">{label(value.reason ?? "")}</span>
      </>
    );
  return (
    <>
      <Exact value={isStat(value) ? value.value : value} />
      {unit && <span className="muted"> {unit}</span>}
    </>
  );
}
function unitOf(kind: string, units: Data, sym: string) {
  if (kind === "price") return units.price ?? "";
  if (kind === "ratio") return units.returns ?? "ratio";
  if (kind === "base") return units.base_volume?.[sym] ?? "";
  if (kind === "quote") return units.quote_volume ?? "";
  return "count";
}
function Profiles({
  spec,
  summary,
  results,
}: {
  spec: Data;
  summary: Data;
  results: Data | null;
}) {
  const symbols = (spec.symbols as string[]).filter(
    (s) => summary.profiles?.[s],
  );
  const units = summary.units ?? {};
  const cross = symbols.length > 1;
  const rows = PROFILE.filter(([, key]) =>
    symbols.some((s) => summary.profiles[s][key] !== undefined),
  );
  const observations = new Set(
    symbols.flatMap((s) =>
      rows
        .map(([, key]) => summary.profiles[s][key])
        .filter(isStat)
        .map((v) => v.observation_count),
    ),
  );
  const extra = Object.fromEntries(
    Object.entries(summary).filter(([k]) => !KNOWN.has(k)),
  );
  const spikes = symbols.map(
    (s) => (summary.profiles[s].volume_spikes ?? []) as Data[],
  );
  const shared = cross
    ? spikes[0].find((a) =>
        spikes.slice(1).every((list) => list.some((b) => b.start === a.start)),
      )?.start
    : undefined;
  const clusters = (summary.clusters ?? []) as Data[];
  return (
    <section
      className={cross ? "section" : "split"}
      data-testid="numerical-summary"
      aria-label="Numerical summary"
    >
      <div className={cross ? "section" : "grow section"}>
        {symbols.length > 0 && (
          <>
            <div className="section-head">
              <h2>{cross ? "Profiles side by side" : "Profile"}</h2>
              {observations.size === 1 && (
                <span className="muted">
                  every statistic uses {[...observations][0]} observations
                  {cross ? " per asset" : ""}
                </span>
              )}
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Metric</th>
                    {cross ? (
                      symbols.map((s, i) => (
                        <th className="num" key={s}>
                          <Pair symbol={s} series={i} small />
                        </th>
                      ))
                    ) : (
                      <th className="num">Exact value</th>
                    )}
                    <th>Unit</th>
                    {!cross && observations.size > 1 && (
                      <th className="num">Obs.</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(([name, key, kind]) => (
                    <tr key={key}>
                      <td className="muted">{name}</td>
                      {symbols.map((s) => (
                        <td className="num" key={s}>
                          <Value
                            value={summary.profiles[s][key]}
                            unit={
                              cross && kind === "base"
                                ? unitOf(kind, units, s)
                                : undefined
                            }
                          />
                        </td>
                      ))}
                      <td className="muted">
                        {cross && kind === "base"
                          ? "base asset"
                          : unitOf(kind, units, symbols[0])}
                      </td>
                      {!cross && observations.size > 1 && (
                        <td className="num muted">
                          {isStat(summary.profiles[symbols[0]][key])
                            ? summary.profiles[symbols[0]][key]
                                .observation_count
                            : ""}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {Object.keys(extra).length > 0 && (
          <div className="panel">
            <DataView data={extra} />
          </div>
        )}
        {results && (
          <details>
            <summary>All result values</summary>
            <DataView data={results} />
          </details>
        )}
      </div>
      {symbols.length > 0 && (
        <div className={cross ? "spread" : "side"}>
          <div className="section">
            {clusters.length > 0 && (
              <>
                <div className="section-head">
                  <h2>Clusters</h2>
                  <span className="muted">{clusters.length} found</span>
                </div>
                <ul className="spikes">
                  {clusters.map((c) => (
                    <li key={c.start}>
                      <span>
                        {minuteLabel(c.start)} to {minuteLabel(c.end)}
                      </span>
                      <span className="muted">{c.bar_count} bars</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <h2>Volume spikes</h2>
            {spikes.every((list) => !list.length) && (
              <p className="muted">No volume spikes.</p>
            )}
            {symbols.map((s, i) =>
              spikes[i].length ? (
                <ul className="spikes" key={s}>
                  {cross && (
                    <li className="head">
                      <Pair symbol={s} series={i} small />
                    </li>
                  )}
                  {spikes[i].map((spike) => (
                    <li key={spike.start}>
                      <span>{minuteLabel(spike.start)} UTC</span>
                      <span>
                        <Exact value={spike.multiple} />×
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null,
            )}
            <p className="muted">
              Multiples of trailing volume.
              {shared
                ? ` Both assets spiked in the same bar, ${minuteLabel(shared)} UTC.`
                : ""}
            </p>
          </div>
          <div className="section">
            <h2>Warm-up history</h2>
            {symbols.map((s, i) => {
              const h = summary.history?.[s];
              if (!h) return null;
              return (
                <div className="panel" key={s}>
                  {cross && <Pair symbol={s} series={i} small />}
                  <dl className="kv">
                    <div>
                      <dt>First bar</dt>
                      <dd>
                        {h.first_observed_start
                          ? minuteLabel(h.first_observed_start)
                          : NULL}
                      </dd>
                    </div>
                    <div>
                      <dt>Last bar</dt>
                      <dd>
                        {h.last_observed_start
                          ? minuteLabel(h.last_observed_start)
                          : NULL}
                      </dd>
                    </div>
                    <div>
                      <dt>Observed</dt>
                      <dd>{h.observed_bars} bars</dd>
                    </div>
                  </dl>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
function Memo({ run, r }: { run: string; r: ReturnType<typeof useResource> }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const enqueue = async () => {
    setBusy(true);
    try {
      await request(`/v1/research/runs/${run}/memo`, { method: "POST" });
      setError("");
      r.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const state = r.data?.status ?? r.data?.state;
  const waiting =
    r.data && ["pending", "running", "queued", "retry_wait"].includes(state);
  return (
    <section
      className="memo"
      data-testid="memo-panel"
      aria-labelledby="memo-title"
    >
      <div className="toolbar">
        <h2 id="memo-title">Memo</h2>
        {r.data && <Tag value={state} />}
      </div>
      <ErrorBox>{error || r.error}</ErrorBox>
      {r.data?.content && (
        <div className="memo-content">
          {String(r.data.content)
            .split("\n\n")
            .map((p, i) => (
              <p key={i}>{p}</p>
            ))}
        </div>
      )}
      {waiting && (
        <WorkerHint
          kind="memo"
          running={state === "running"}
          since={r.data?.created_at}
        />
      )}
      {r.data?.error && <ErrorBox>{r.data.error}</ErrorBox>}
      {!r.data && r.error.toLowerCase().includes("not found") && (
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void enqueue()}
        >
          Queue a memo
        </button>
      )}
      {(waiting || r.stopped) && <Refresh r={r} />}
    </section>
  );
}
function Hashes({ title, values }: { title: string; values: string[] }) {
  const [all, setAll] = useState(false);
  if (!values.length) return null;
  const shown = all ? values : values.slice(0, 4);
  return (
    <>
      <dt>{title}</dt>
      <dd>
        {shown.map((v) => (
          <ShortId key={v} value={v} label={`${title.toLowerCase()} hash`} />
        ))}
        {values.length > shown.length && (
          <button
            type="button"
            className="icon-button more"
            onClick={() => setAll(true)}
          >
            +{values.length - shown.length}
          </button>
        )}
      </dd>
    </>
  );
}
function Receipt({
  id,
  info,
  memo,
}: {
  id: string;
  info: Data;
  memo: Data | null;
}) {
  const spec = info.spec ?? {};
  const execution = info.fingerprint?.execution ?? {};
  const attempts = (info.attempts ?? []) as Data[];
  const last = attempts[attempts.length - 1];
  const manifests = ((info.fingerprint?.datasets ?? []) as Data[]).map((d) =>
    String(d.manifest_sha256),
  );
  const versions = ((spec.dataset_versions ?? []) as string[]).map(String);
  const groups: [string, string[]][] = [
    ["Versions", versions],
    ["Manifests", manifests],
    ["Summary", memo?.summary_sha256 ? [memo.summary_sha256] : []],
    ["Memo", memo?.memo_sha256 ? [memo.memo_sha256] : []],
  ];
  const terminal = ["succeeded", "failed"].includes(info.state);
  const model = memo?.provenance?.model;
  return (
    <section className="receipt" aria-labelledby="receipt-title">
      <h2 id="receipt-title">Receipt</h2>
      <dl>
        <dt>Run</dt>
        <dd>
          <ShortId value={id} testId="run-id" label="run ID" />
        </dd>
        {info.created_at && (
          <>
            <dt>Submitted</dt>
            <dd>{stamp(info.created_at)}</dd>
          </>
        )}
        {terminal && info.updated_at && (
          <>
            <dt>{info.state === "failed" ? "Failed" : "Completed"}</dt>
            <dd>{stamp(info.updated_at)}</dd>
          </>
        )}
        <dt>Attempts</dt>
        <dd>{info.attempt_count ?? 0} of 3</dd>
        {last?.started_at && last?.ended_at && (
          <>
            <dt>Duration</dt>
            <dd>
              {duration(
                Date.parse(last.ended_at) - Date.parse(last.started_at),
              )}
            </dd>
          </>
        )}
        {groups.map(([title, values]) => (
          <Hashes key={title} title={title} values={values} />
        ))}
        {model && (
          <>
            <dt>Model</dt>
            <dd>
              {model}
              {memo?.provenance?.model_digest && (
                <ShortId
                  value={memo.provenance.model_digest}
                  label="model digest"
                />
              )}
            </dd>
          </>
        )}
        {execution.git_revision && (
          <>
            <dt>Source</dt>
            <dd>
              <code title={execution.git_revision}>
                {String(execution.git_revision).slice(0, 7)}
              </code>
              <span className="muted">
                {execution.numerics}
                {execution.git_dirty ? ", with local changes" : ""}
              </span>
            </dd>
          </>
        )}
      </dl>
      <div className="actions">
        <CopyButton
          text="Copy all hashes"
          label="all hashes"
          value={[
            `run ${id}`,
            ...groups.flatMap(([t, values]) =>
              values.map((v) => `${t.toLowerCase()} ${v}`),
            ),
          ].join("\n")}
        />
      </div>
      <Provenance data={memo ? { run: info, memo } : info} />
    </section>
  );
}
export function ResearchDetail({ id }: { id: string }) {
  const info = useResource(`/v1/research/runs/${id}`, active);
  const data = info.data;
  const spec = data?.spec as Data | undefined;
  const done = data?.state === "succeeded";
  const summary = useResource(done ? `/v1/research/runs/${id}/summary` : null);
  const results = useResource(done ? `/v1/research/runs/${id}/results` : null);
  const memo = useResource(
    done ? `/v1/research/runs/${id}/memo` : null,
    active,
  );
  const pinned = useCatalogRows(
    spec
      ? {
          start_date: spec.history_start.slice(0, 10),
          before_date: nextDay(lastDay(spec.end)),
        }
      : null,
  );
  const rows =
    spec &&
    pinned.rows &&
    spec.dataset_versions.every((id: string) =>
      pinned.rows!.some((row) => row.dataset_version_id === id),
    )
      ? pinned.rows.filter((v) =>
          spec.dataset_versions.includes(v.dataset_version_id),
        )
      : null;
  const venues = [
    ...new Set((rows ?? []).map((v) => venueName(v.venue)).filter(Boolean)),
  ];
  const symbols = (spec?.symbols ?? []) as string[];
  return (
    <>
      <PageTitle
        title={
          spec ? (TITLES[spec.workflow] ?? "Research run") : "Research run"
        }
        meta={
          spec && (
            <div className="pairs">
              {symbols.map((s, i) => (
                <Fragment key={s}>
                  {i > 0 && <span className="muted">vs</span>}
                  <Pair symbol={s} series={i} />
                </Fragment>
              ))}
              {venues.length > 0 && (
                <span className="muted">{venues.join(", ")}</span>
              )}
            </div>
          )
        }
      >
        {data && (
          <div className="title-actions">
            <Tag value={data.state} />
            {spec && (
              <CopyButton
                value={JSON.stringify(spec, null, 2)}
                label="spec"
                text="Copy spec"
              />
            )}
          </div>
        )}
      </PageTitle>
      <ErrorBox>{info.error}</ErrorBox>
      {data && spec && (
        <>
          <WindowTrack spec={spec} />
          {active(data) && (
            <WorkerHint
              kind="research"
              id={id}
              since={data.created_at}
              running={data.state === "running"}
            />
          )}
          {data.error && <ErrorBox>{data.error}</ErrorBox>}
          {data.state !== "failed" && (
            <Figures spec={spec} summary={summary.data} />
          )}
          {done && (
            <>
              <ErrorBox>{summary.error}</ErrorBox>
              <ErrorBox>{pinned.error}</ErrorBox>
              {pinned.error && (
                <button className="secondary" onClick={pinned.refresh}>
                  Retry pinned version lookup
                </button>
              )}
              {pinned.truncated && !rows && (
                <section className="notice">
                  <p>
                    More catalog metadata is needed to locate every pinned
                    version.
                  </p>
                  <button disabled={pinned.busy} onClick={pinned.loadMore}>
                    Load more pinned version metadata
                  </button>
                </section>
              )}
              {pinned.rows && !pinned.truncated && !rows && !pinned.error && (
                <ErrorBox>
                  Some pinned versions are missing from the registered catalog.
                </ErrorBox>
              )}
              <CloseChart spec={spec} rows={rows} />
              <BarsChart spec={spec} results={results.data} />
              <ErrorBox>{results.error}</ErrorBox>
              {summary.data && (
                <Profiles
                  spec={spec}
                  summary={summary.data}
                  results={results.data}
                />
              )}
            </>
          )}
          <div className="split">
            {done && (
              <div className="grow">
                <Memo run={id} r={memo} />
              </div>
            )}
            <div className="side">
              <Receipt id={id} info={data} memo={memo.data} />
            </div>
          </div>
        </>
      )}
      {!done && <Refresh r={info} />}
    </>
  );
}
