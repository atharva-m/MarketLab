import { useState } from "react";
import { selectedVersions, setSelectedVersions, type Data } from "./client";
import { useResource } from "./hooks";
import {
  DataView,
  ErrorBox,
  PageTitle,
  Refresh,
  Tag,
  label,
} from "./components";
export function Catalog() {
  const [symbol, setSymbol] = useState("");
  const [cursor, setCursor] = useState("");
  const [trail, setTrail] = useState<string[]>([]);
  const [selected, setSelected] = useState<Data[]>(selectedVersions);
  const [detail, setDetail] = useState("");
  const query = new URLSearchParams({
    limit: "25",
    ...(symbol ? { symbol } : {}),
    ...(cursor ? { cursor } : {}),
  });
  const r = useResource(`/v1/datasets?${query}`);
  const inspection = useResource(detail ? `/v1/datasets/${detail}` : null);
  const toggle = (row: Data) => {
    const next = selected.some(
      (v) => v.dataset_version_id === row.dataset_version_id,
    )
      ? selected.filter((v) => v.dataset_version_id !== row.dataset_version_id)
      : [...selected, row];
    if (next.length > 62) return;
    setSelected(next);
    setSelectedVersions(next);
  };
  return (
    <>
      <PageTitle eyebrow="DATA FOUNDATION" title="Dataset catalog">
        <a className="button" href="#/research/new">
          Research with {selected.length} selected
        </a>
      </PageTitle>
      <p className="intro">
        Registered daily partitions, with immutable identities and traceable
        sources. Catalog metadata is not a fresh artifact verification.
      </p>
      <section className="panel">
        <div className="toolbar">
          <label>
            Symbol
            <select
              value={symbol}
              onChange={(e) => {
                setSymbol(e.target.value);
                setCursor("");
                setTrail([]);
              }}
            >
              <option value="">Both assets</option>
              <option>BTCUSDT</option>
              <option>ETHUSDT</option>
            </select>
          </label>
          <span className="selection-count">
            {selected.length} / 62 versions selected explicitly
          </span>
          <button
            className="secondary"
            onClick={() => {
              setSelected([]);
              setSelectedVersions([]);
            }}
          >
            Clear selection
          </button>
        </div>
        <ErrorBox>{r.error}</ErrorBox>
        {r.busy && !r.data && <p role="status">Loading catalog…</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Select</th>
                <th>Asset / UTC day</th>
                <th>Accepted rows</th>
                <th>Version identity</th>
                <th>Verification</th>
              </tr>
            </thead>
            <tbody>
              {r.data?.items.map((row: Data) => (
                <tr key={row.dataset_version_id}>
                  <td>
                    <input
                      aria-label={`Select ${row.symbol} ${row.trade_date} ${row.dataset_version_id}`}
                      type="checkbox"
                      checked={selected.some(
                        (v) => v.dataset_version_id === row.dataset_version_id,
                      )}
                      onChange={() => toggle(row)}
                    />
                  </td>
                  <td>
                    <strong>{row.symbol}</strong>
                    <br />
                    <span className="muted">{row.trade_date}</span>
                  </td>
                  <td className="exact">{row.row_count}</td>
                  <td>
                    <button
                      className="identity"
                      onClick={() => setDetail(row.dataset_version_id)}
                      title={row.dataset_version_id}
                    >
                      {row.dataset_version_id}
                    </button>
                  </td>
                  <td>
                    <Tag value="registered metadata" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {r.data?.items.length === 0 && (
          <p>No registered versions match this filter.</p>
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
          <span>Current committed catalog · 25 per page</span>
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
      {detail && (
        <section className="panel">
          <div className="toolbar">
            <h2>Dataset verification</h2>
            <button className="secondary" onClick={() => setDetail("")}>
              Close detail
            </button>
          </div>
          <p className="exact">{detail}</p>
          <ErrorBox>{inspection.error}</ErrorBox>
          {inspection.busy && (
            <p role="status">Verifying complete registered artifacts…</p>
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
export function JobList() {
  const [kind, setKind] = useState("research");
  const [cursor, setCursor] = useState("");
  const [trail, setTrail] = useState<string[]>([]);
  const paths: Data = {
    research: "/v1/research/runs",
    ingestion: "/v1/ingestion/submissions",
    copilot: "/v1/copilot/requests",
  };
  const r = useResource(
    `${paths[kind]}?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
  );
  return (
    <>
      <PageTitle eyebrow="DURABLE EXECUTION" title="Jobs and submissions" />
      <section className="panel">
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
            <option value="research">Research runs</option>
            <option value="ingestion">Ingestion submissions</option>
            <option value="copilot">Copilot requests</option>
          </select>
        </label>
        <ErrorBox>{r.error}</ErrorBox>
        <div className="job-list">
          {r.data?.items.map((item: Data) => {
            const id =
              item.run_id && kind === "research"
                ? item.run_id
                : (item.submission_id ?? item.request_id);
            return (
              <a
                className="job"
                key={id}
                href={`#/${kind === "research" ? "runs" : kind}/${id}`}
              >
                <div>
                  <strong>{label(item.workflow ?? kind)}</strong>
                  <small>{item.created_at}</small>
                  <code>{id}</code>
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
        {r.data?.items.length === 0 && <p>No submissions found.</p>}
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
        <Refresh r={r} />
      </section>
    </>
  );
}
