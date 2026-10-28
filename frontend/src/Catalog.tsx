import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  request,
  selectedVersions,
  setSelectedVersions,
  type Data,
} from "./client";
import { useResource } from "./hooks";
import { DataView, ErrorBox, PageTitle, Refresh, Tag } from "./components";
import {
  dayLabel,
  dayRange,
  Pair,
  pairText,
  runName,
  ShortId,
  splitPair,
  stamp,
  venueName,
} from "./ui";
const TIERS = ["t1", "t2", "t3", "t4", "t5"];
const FILLS = [
  "var(--ti-1)",
  "var(--ti-2)",
  "var(--ti-3)",
  "var(--ti-4)",
  "var(--ti-5)",
];
const PAGE = 25;
const count = (row: Data) => BigInt(String(row.row_count ?? 0));
const grouped = (n: bigint) => n.toLocaleString("en-US");
const millions = (n: bigint) => {
  const value = Number(n) / 1e6;
  return value >= 10 ? `${Math.round(value)}M` : `${value.toFixed(1)}M`;
};
const nextDay = (date: string) =>
  new Date(Date.parse(`${date}T00:00:00Z`) + 86_400_000)
    .toISOString()
    .slice(0, 10);
/**
 * Reads every registered version for the summary strip and day matrix, one
 * bounded metadata page after another. A server-side catalog summary should
 * replace this if the catalog grows past a few pages.
 */
export function useCatalogRows(filters: Record<string, string> | null) {
  const key = filters ? new URLSearchParams(filters).toString() : null;
  const [state, setState] = useState<{
    key: string | null;
    rows: Data[] | null;
    error: string;
    truncated: boolean;
    cursor: string;
  }>({ key: null, rows: null, error: "", truncated: false, cursor: "" });
  const [epoch, setEpoch] = useState(0);
  const [continuation, setContinuation] = useState<{
    key: string;
    rows: Data[];
    cursor: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    setBusy(true);
    void (async () => {
      const previous = continuation?.key === key ? continuation : null;
      const rows: Data[] = [...(previous?.rows ?? [])];
      let cursor = previous?.cursor ?? "";
      let pages = 0;
      try {
        do {
          const query = new URLSearchParams(key);
          query.set("limit", "100");
          if (cursor) query.set("cursor", cursor);
          const { data } = await request(`/v1/datasets?${query}`, {
            signal: controller.signal,
          });
          rows.push(...((data.items ?? []) as Data[]));
          cursor = data.next_cursor ?? "";
          pages++;
        } while (cursor && pages < 10);
        if (!controller.signal.aborted)
          setState({
            key,
            rows,
            error: "",
            truncated: Boolean(cursor),
            cursor,
          });
      } catch (e) {
        if (!controller.signal.aborted)
          setState({
            key,
            rows: null,
            error: e instanceof Error ? e.message : "Request failed",
            truncated: false,
            cursor: "",
          });
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    })();
    return () => controller.abort();
  }, [key, epoch, continuation]);
  const current = state.key === key;
  return {
    rows: current ? state.rows : null,
    error: current ? state.error : "",
    truncated: current && state.truncated,
    busy,
    loadMore: () => {
      if (key !== null && current && state.rows && state.cursor && !busy)
        setContinuation({ key, rows: state.rows, cursor: state.cursor });
    },
    refresh: () => {
      setContinuation(null);
      setEpoch((v) => v + 1);
    },
  };
}
/** Five equal-count tiers of daily trades; equal counts share a tier. */
function tiers(rows: Data[]) {
  const sorted = rows.map(count).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const tierOf = (n: bigint) => {
    const rank = sorted.findIndex((v) => v === n);
    return Math.min(
      4,
      Math.floor((Math.max(0, rank) * 5) / Math.max(1, sorted.length)),
    );
  };
  const upper: (bigint | undefined)[] = [];
  for (const n of sorted) upper[tierOf(n)] = n;
  return { tierOf, upper };
}
export function Catalog({ inspect = "" }: { inspect?: string }) {
  const catalog = useCatalogRows({});
  const rows = catalog.rows;
  const [selected, setSelected] = useState<Data[]>(selectedVersions);
  const [detail, setDetail] = useState(inspect);
  const [symbol, setSymbol] = useState("");
  const [day, setDay] = useState("");
  const [page, setPage] = useState(0);
  const anchor = useRef<{ symbol: string; date: string } | null>(null);
  const drag = useRef<{ add: boolean; moved: boolean; start: Data } | null>(
    null,
  );
  const dragged = useRef(false);
  const latest = useRef(selected);
  latest.current = selected;
  const table = useRef<HTMLElement>(null);
  const inspection = useResource(detail ? `/v1/datasets/${detail}` : null);
  const isSelected = (row: Data) =>
    latest.current.some((v) => v.dataset_version_id === row.dataset_version_id);
  const commit = (next: Data[]) => {
    if (next.length > 62) return;
    latest.current = next;
    setSelected(next);
    setSelectedVersions(next);
  };
  const toggle = (row: Data) =>
    commit(
      isSelected(row)
        ? latest.current.filter(
            (v) => v.dataset_version_id !== row.dataset_version_id,
          )
        : [...latest.current, row],
    );
  const apply = (targets: Data[], add: boolean) => {
    const ids = new Set(targets.map((v) => v.dataset_version_id));
    const kept = latest.current.filter((v) => !ids.has(v.dataset_version_id));
    commit(add ? [...kept, ...targets] : kept);
  };
  const view = useMemo(() => {
    if (!rows?.length) return null;
    const symbols = [...new Set(rows.map((v) => String(v.symbol)))].sort();
    const dates = rows.map((v) => String(v.trade_date)).sort();
    const first = dates[0];
    const last = dates[dates.length - 1];
    const days: string[] = [];
    for (let d = first; d <= last && days.length < 400; d = nextDay(d))
      days.push(d);
    const cells = new Map<string, Data[]>();
    for (const row of rows) {
      const k = `${row.symbol} ${row.trade_date}`;
      cells.set(k, [...(cells.get(k) ?? []), row]);
    }
    const venues = [
      ...new Set(rows.map((v) => venueName(v.venue)).filter(Boolean)),
    ];
    return {
      symbols,
      days,
      cells,
      first,
      last,
      venues,
      total: rows.reduce((sum, v) => sum + count(v), 0n),
      ...tiers(rows),
    };
  }, [rows]);
  useEffect(() => {
    const end = () => {
      dragged.current = Boolean(drag.current?.moved);
      drag.current = null;
      setTimeout(() => {
        dragged.current = false;
      }, 0);
    };
    window.addEventListener("pointerup", end);
    return () => window.removeEventListener("pointerup", end);
  }, []);
  const single = (sym: string, date: string) => {
    const versions = view?.cells.get(`${sym} ${date}`) ?? [];
    return versions.length === 1 ? versions[0] : null;
  };
  const cellClick = (sym: string, date: string, shift: boolean) => {
    if (!view) return;
    const versions = view.cells.get(`${sym} ${date}`) ?? [];
    if (versions.length > 1) {
      setSymbol(sym);
      setDay(date);
      setPage(0);
      table.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    const row = versions[0];
    if (!row) return;
    const from = anchor.current;
    if (shift && from && from.symbol === sym) {
      const [a, b] = [from.date, date].sort();
      const range = view.days
        .filter((d) => d >= a && d <= b)
        .map((d) => single(sym, d))
        .filter((v): v is Data => Boolean(v));
      apply(range, !isSelected(row));
    } else toggle(row);
    anchor.current = { symbol: sym, date };
  };
  const listed = (rows ?? [])
    .filter(
      (v) => (!symbol || v.symbol === symbol) && (!day || v.trade_date === day),
    )
    .sort(
      (a, b) =>
        String(b.published_at ?? "").localeCompare(
          String(a.published_at ?? ""),
        ) ||
        String(b.trade_date).localeCompare(String(a.trade_date)) ||
        String(a.symbol).localeCompare(String(b.symbol)),
    );
  const pages = Math.max(1, Math.ceil(listed.length / PAGE));
  const shown = listed.slice(page * PAGE, page * PAGE + PAGE);
  const picked = [...selected].sort(
    (a, b) =>
      String(a.symbol).localeCompare(String(b.symbol)) ||
      String(a.trade_date).localeCompare(String(b.trade_date)),
  );
  const pickedDates = picked.map((v) => String(v.trade_date)).sort();
  const pickedSymbols = [...new Set(picked.map((v) => String(v.symbol)))];
  const pickedTrades = picked.reduce((sum, v) => sum + count(v), 0n);
  return (
    <>
      <PageTitle title="Datasets" />
      <ErrorBox>{catalog.error}</ErrorBox>
      {catalog.error && (
        <div className="actions">
          <button className="secondary" onClick={catalog.refresh}>
            Try again
          </button>
        </div>
      )}
      {!rows && !catalog.error && <p role="status">Loading datasets…</p>}
      {rows?.length === 0 && (
        <section className="notice">
          <p>No datasets yet.</p>
          <a className="button" href="#/ingestion/new">
            Ingest daily trades
          </a>
        </section>
      )}
      {view && (
        <>
          <dl className="strip">
            <div>
              <dt>Versions</dt>
              <dd>{grouped(BigInt(rows!.length))}</dd>
            </div>
            <div>
              <dt>Trades</dt>
              <dd>{grouped(view.total)}</dd>
            </div>
            <div>
              <dt>Days</dt>
              <dd>{dayRange(view.first, view.last, true)}</dd>
            </div>
            <div>
              <dt>Assets</dt>
              <dd>{view.symbols.map(pairText).join(", ")}</dd>
            </div>
            {view.venues.length > 0 && (
              <div>
                <dt>Venue</dt>
                <dd>{view.venues.join(", ")}</dd>
              </div>
            )}
          </dl>
          {catalog.truncated && (
            <div className="actions">
              <p className="muted">
                Showing {rows!.length} versions. More registered versions are
                available.
              </p>
              <button
                className="secondary"
                disabled={catalog.busy}
                onClick={catalog.loadMore}
              >
                {catalog.busy ? "Loading more versions…" : "Load more versions"}
              </button>
            </div>
          )}
          <section className="section" aria-labelledby="matrix-title">
            <div className="section-head">
              <h2 id="matrix-title">Trades per day</h2>
              <span className="muted">
                Click a day to pin it. Shift-click or drag selects a range.
              </span>
            </div>
            <div className="matrix-panel">
              <div
                className="matrix"
                style={{ "--days": view.days.length } as CSSProperties}
              >
                <div className="matrix-row days" aria-hidden="true">
                  <span />
                  {view.days.map((d) => (
                    <span key={d}>{Number(d.slice(8, 10))}</span>
                  ))}
                </div>
                {view.symbols.map((sym, series) => (
                  <div className="matrix-row" key={sym}>
                    <Pair symbol={sym} series={series} small />
                    {view.days.map((date) => {
                      const versions = view.cells.get(`${sym} ${date}`) ?? [];
                      if (!versions.length)
                        return (
                          <span
                            key={date}
                            className="cell empty"
                            title={`${pairText(sym)}, ${dayLabel(date)}: no version`}
                          />
                        );
                      const most = versions.reduce((m, v) =>
                        count(v) > count(m) ? v : m,
                      );
                      const tier = view.tierOf(count(most));
                      const pinned = versions.some(isSelected);
                      const many = versions.length > 1;
                      const text = `${pairText(sym)}, ${dayLabel(date)}: ${grouped(count(most))} trades`;
                      return (
                        <button
                          key={date}
                          type="button"
                          className={`cell ${TIERS[tier]}`}
                          aria-pressed={many ? undefined : pinned}
                          aria-label={
                            many ? `${text}, ${versions.length} versions` : text
                          }
                          title={
                            many ? `${text}, ${versions.length} versions` : text
                          }
                          onPointerDown={(e) => {
                            if (many || e.button !== 0) return;
                            drag.current = {
                              add: !pinned,
                              moved: false,
                              start: versions[0],
                            };
                          }}
                          onPointerEnter={() => {
                            const d = drag.current;
                            if (!d || many) return;
                            if (!d.moved) {
                              d.moved = true;
                              apply([d.start, versions[0]], d.add);
                            } else apply([versions[0]], d.add);
                          }}
                          onClick={(e) => {
                            if (dragged.current) return;
                            cellClick(sym, date, e.shiftKey);
                          }}
                        >
                          {many ? versions.length : ""}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
              <div className="legend" aria-hidden="true">
                {view.upper.map((n, i) =>
                  n === undefined ? null : (
                    <span key={i}>
                      <i style={{ background: FILLS[i] }} />
                      {i === view.upper.length - 1 && i > 0
                        ? `> ${millions(view.upper[i - 1] ?? n)}`
                        : `≤ ${millions(n)}`}
                    </span>
                  ),
                )}
                <span>trades per day</span>
              </div>
            </div>
          </section>
          <section className="selection" aria-label="Selection">
            <div>
              {picked.length ? (
                <>
                  <div className="summary-line">
                    <strong>
                      {picked.length}{" "}
                      {picked.length === 1 ? "version" : "versions"}
                    </strong>
                    <span className="muted">
                      {dayRange(
                        pickedDates[0],
                        pickedDates[pickedDates.length - 1],
                      )}
                    </span>
                    <span className="muted">
                      {pickedSymbols.map(pairText).join(", ")}
                    </span>
                    <span className="muted">
                      {grouped(pickedTrades)} trades
                    </span>
                  </div>
                  <div className="chips">
                    {picked.slice(0, 8).map((v) => (
                      <span className="chip" key={v.dataset_version_id}>
                        {splitPair(String(v.symbol))[0]}{" "}
                        {dayLabel(String(v.trade_date))}
                      </span>
                    ))}
                    {picked.length > 8 && (
                      <span className="chip">+{picked.length - 8} more</span>
                    )}
                  </div>
                </>
              ) : (
                <span className="muted">
                  Select days above to pin exact versions for research.
                </span>
              )}
            </div>
            <div className="actions">
              <button
                className="secondary"
                disabled={!picked.length}
                onClick={() => commit([])}
              >
                Clear
              </button>
              <a className="button" href="#/research/new">
                Research with {selected.length} selected
              </a>
            </div>
          </section>
          <section
            className="section"
            ref={table}
            aria-labelledby="versions-title"
          >
            <div className="section-head">
              <h2 id="versions-title">Versions</h2>
              <div className="actions">
                {day && (
                  <button className="secondary" onClick={() => setDay("")}>
                    {dayLabel(day)} only, show all days
                  </button>
                )}
                <select
                  aria-label="Asset"
                  value={symbol}
                  onChange={(e) => {
                    setSymbol(e.target.value);
                    setPage(0);
                  }}
                >
                  <option value="">All assets</option>
                  {view.symbols.map((s) => (
                    <option key={s} value={s}>
                      {pairText(s)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>
                      <span className="sr-only">Selected</span>
                    </th>
                    <th>Asset</th>
                    <th>UTC day</th>
                    <th className="num">Trades</th>
                    <th>Version</th>
                    <th>Published</th>
                    <th>
                      <span className="sr-only">Integrity</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((row) => (
                    <tr key={row.dataset_version_id}>
                      <td>
                        <input
                          aria-label={`Select ${row.symbol} ${row.trade_date} ${row.dataset_version_id}`}
                          type="checkbox"
                          checked={isSelected(row)}
                          onChange={() => toggle(row)}
                        />
                      </td>
                      <td>
                        <Pair
                          symbol={String(row.symbol)}
                          series={view.symbols.indexOf(String(row.symbol))}
                          small
                        />
                      </td>
                      <td>{row.trade_date}</td>
                      <td className="num exact">{row.row_count}</td>
                      <td>
                        <ShortId
                          value={String(row.dataset_version_id)}
                          label="version ID"
                        />
                      </td>
                      <td className="muted">
                        {row.published_at
                          ? stamp(String(row.published_at))
                          : ""}
                      </td>
                      <td className="num">
                        <button
                          className="secondary"
                          onClick={() =>
                            setDetail(String(row.dataset_version_id))
                          }
                        >
                          Verify
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {listed.length === 0 && (
              <p className="muted">No versions match this filter.</p>
            )}
            <div className="pagination">
              <button
                className="secondary"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                Previous page
              </button>
              <span>
                {listed.length
                  ? `${page * PAGE + 1}–${Math.min(listed.length, page * PAGE + PAGE)} of ${listed.length}`
                  : ""}
              </span>
              <button
                className="secondary"
                disabled={page >= pages - 1}
                onClick={() => setPage(page + 1)}
              >
                Next page
              </button>
            </div>
          </section>
        </>
      )}
      {detail && (
        <section className="panel" aria-labelledby="verification-title">
          <div className="toolbar">
            <h2 id="verification-title">Dataset verification</h2>
            <button className="secondary" onClick={() => setDetail("")}>
              Close
            </button>
          </div>
          <ShortId value={detail} label="version ID" />
          <ErrorBox>{inspection.error}</ErrorBox>
          {inspection.busy && (
            <p role="status">Verifying every registered artifact…</p>
          )}
          {inspection.data && (
            <>
              <Tag value={inspection.data.verification} />
              <DataView data={inspection.data.manifest} />
            </>
          )}
        </section>
      )}
    </>
  );
}
const FAMILIES: Record<string, [string, string]> = {
  research: ["/v1/research/runs", "Research runs"],
  ingestion: ["/v1/ingestion/submissions", "Ingestion submissions"],
  copilot: ["/v1/copilot/requests", "Copilot requests"],
};
export function JobList() {
  const [kind, setKind] = useState("research");
  const [cursor, setCursor] = useState("");
  const [trail, setTrail] = useState<string[]>([]);
  const r = useResource(
    `${FAMILIES[kind][0]}?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
  );
  return (
    <>
      <PageTitle title="Jobs" />
      <section className="panel">
        <div className="toolbar">
          <label>
            Job family
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setCursor("");
                setTrail([]);
              }}
            >
              {Object.entries(FAMILIES).map(([value, [, title]]) => (
                <option key={value} value={value}>
                  {title}
                </option>
              ))}
            </select>
          </label>
          <Refresh r={r} />
        </div>
        <ErrorBox>{r.error}</ErrorBox>
        {r.data && r.data.items.length > 0 && (
          <div className="job-list">
            {r.data.items.map((item: Data) => {
              const id =
                item.run_id && kind === "research"
                  ? item.run_id
                  : (item.submission_id ?? item.request_id);
              const name =
                kind === "research"
                  ? runName(item)
                  : kind === "ingestion"
                    ? "Ingestion"
                    : "Copilot request";
              return (
                <a
                  className="job"
                  key={id}
                  href={`#/${kind === "research" ? "runs" : kind}/${id}`}
                >
                  <div>
                    <strong>{name}</strong>
                    {item.symbols && kind !== "research" && (
                      <small>
                        {(item.symbols as string[]).map(pairText).join(", ")}
                      </small>
                    )}
                    <ShortId value={String(id)} copy={false} />
                    {item.created_at && (
                      <small>{stamp(String(item.created_at))}</small>
                    )}
                  </div>
                  <Tag
                    value={
                      item.state ??
                      (item.succeeded === item.total ? "succeeded" : "partial")
                    }
                  />
                </a>
              );
            })}
          </div>
        )}
        {r.data?.items.length === 0 && (
          <p className="muted">Nothing here yet.</p>
        )}
        <div className="pagination">
          <button
            className="secondary"
            disabled={!trail.length}
            onClick={() => {
              setCursor(trail.at(-1) ?? "");
              setTrail(trail.slice(0, -1));
            }}
          >
            Previous page
          </button>
          <button
            className="secondary"
            disabled={!r.data?.next_cursor}
            onClick={() => {
              setTrail([...trail, cursor]);
              setCursor(r.data?.next_cursor);
            }}
          >
            Next page
          </button>
        </div>
      </section>
    </>
  );
}
