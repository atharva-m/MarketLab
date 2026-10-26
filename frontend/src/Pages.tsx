import { useEffect, useState, type FormEvent } from "react";
import {
  request,
  researchSpec,
  selectedVersions,
  versionIDs,
  type Data,
} from "./client";
import { navigate, useResource } from "./hooks";
import {
  active,
  DataView,
  ErrorBox,
  label,
  PageTitle,
  Provenance,
  Refresh,
  Tag,
  useMutation,
  VersionInput,
  WorkerNotice,
} from "./components";
import { BarsChart } from "./Chart";
export function ResearchForm() {
  const [versions, setVersions] = useState(() =>
    selectedVersions()
      .map((v) => v.dataset_version_id)
      .join("\n"),
  );
  const [form, setForm] = useState<Data>({
    workflow: "market_profile",
    symbol: "BTCUSDT",
    start: "2025-01-01T01:00:00Z",
    end: "2025-02-01T00:00:00Z",
    history_start: "2025-01-01T00:00:00Z",
    metrics: ["profile"],
  });
  const [validation, setValidation] = useState("");
  const mutation = useMutation("research.new", "/v1/research/runs", (d) =>
    navigate(`/runs/${d.run_id}`),
  );
  const metrics =
    form.workflow === "market_profile"
      ? ["profile"]
      : form.workflow === "cross_asset"
        ? ["profile", "correlation", "close_change_difference"]
        : ["profile", "clusters"];
  const field = (name: string, value: string) =>
    setForm({ ...form, [name]: value });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setValidation("");
    try {
      mutation.submit(JSON.stringify(researchSpec(form, versionIDs(versions))));
    } catch (e) {
      setValidation((e as Error).message);
    }
  };
  return (
    <>
      <PageTitle eyebrow="DETERMINISTIC ANALYSIS" title="New research run" />
      <p className="intro">
        Pin the data and describe the evaluation. Numerical execution is
        independent of Ollama; the server verifies coverage and warm-up before
        accepting a run.
      </p>
      <form className="panel form-grid" onSubmit={submit}>
        <label>
          Workflow
          <select
            aria-label="Workflow"
            value={form.workflow}
            onChange={(e) =>
              setForm({
                ...form,
                workflow: e.target.value,
                metrics:
                  e.target.value === "cross_asset"
                    ? ["profile", "correlation", "close_change_difference"]
                    : e.target.value === "volatility_cluster"
                      ? ["profile", "clusters"]
                      : ["profile"],
              })
            }
          >
            <option value="market_profile">
              Market profile · descriptive OHLCV
            </option>
            <option value="cross_asset">Cross asset · BTC / ETH</option>
            <option value="volatility_cluster">Volatility clusters</option>
          </select>
        </label>
        <label>
          Asset
          <select
            aria-label="Asset"
            disabled={form.workflow === "cross_asset"}
            value={form.symbol}
            onChange={(e) => field("symbol", e.target.value)}
          >
            <option>BTCUSDT</option>
            <option>ETHUSDT</option>
          </select>
        </label>
        <label>
          Evaluation start (UTC, inclusive)
          <input
            data-testid="evaluation-start"
            required
            value={form.start}
            onChange={(e) => field("start", e.target.value)}
          />
        </label>
        <label>
          Evaluation end (UTC, exclusive)
          <input
            data-testid="evaluation-end"
            required
            value={form.end}
            onChange={(e) => field("end", e.target.value)}
          />
        </label>
        <label>
          History start (UTC)
          <input
            data-testid="history-start"
            required
            value={form.history_start}
            onChange={(e) => field("history_start", e.target.value)}
          />
          <small>
            12 prior bars for profile/cross asset; clusters need 300 prior bars.
          </small>
        </label>
        <fieldset>
          <legend>Summary metrics</legend>
          {metrics.map((metric) => (
            <label className="check" key={metric}>
              <input
                type="checkbox"
                checked={form.metrics.includes(metric)}
                onChange={(e) =>
                  setForm({
                    ...form,
                    metrics: e.target.checked
                      ? [...form.metrics, metric]
                      : form.metrics.filter((v: string) => v !== metric),
                  })
                }
              />
              {label(metric)}
            </label>
          ))}
        </fieldset>
        <VersionInput value={versions} onChange={setVersions} />
        <p className="notice wide">
          Fixed interval: 5 minutes. Cluster rules: volatility quantile 0.9,
          volume multiple 2, minimum 2 bars. History is separate from
          evaluation. No missing bars are filled.
        </p>
        <div className="wide">
          <ErrorBox>{validation}</ErrorBox>
          {mutation.panel}
          <button
            data-testid="submit-research"
            disabled={mutation.busy}
            type="submit"
          >
            {mutation.busy
              ? "Validating data and history…"
              : "Submit research run"}
          </button>
          {mutation.busy && (
            <p role="status">
              Validation can take several minutes within the existing 30-minute
              bound. Keep this page open; a run is queued only after acceptance.
            </p>
          )}
        </div>
      </form>
    </>
  );
}
export function Ingestion() {
  const [symbols, setSymbols] = useState(["BTCUSDT"]);
  const [start, setStart] = useState("2025-01-01");
  const [end, setEnd] = useState("2025-01-02");
  const m = useMutation("ingestion.new", "/v1/ingestion/submissions", (d) =>
    navigate(`/ingestion/${d.submission_id}`),
  );
  return (
    <>
      <PageTitle eyebrow="OFFICIAL HISTORICAL DATA" title="Submit ingestion" />
      <p className="intro">
        Request official January daily archives. Existing workers download,
        validate and publish immutable versions; a fresh operation rechecks the
        source.
      </p>
      <form
        className="panel form-grid"
        onSubmit={(e) => {
          e.preventDefault();
          m.submit(
            JSON.stringify({
              schema: "ingestion-submission-v1",
              symbols: [...symbols].sort(),
              start_date: start,
              before_date: end,
            }),
          );
        }}
      >
        <fieldset>
          <legend>Assets</legend>
          {["BTCUSDT", "ETHUSDT"].map((s) => (
            <label className="check" key={s}>
              <input
                type="checkbox"
                checked={symbols.includes(s)}
                onChange={(e) =>
                  setSymbols(
                    e.target.checked
                      ? [...symbols, s]
                      : symbols.filter((v) => v !== s),
                  )
                }
              />
              {s}
            </label>
          ))}
        </fieldset>
        <p>At most 62 daily jobs. Partial completion remains explicit.</p>
        <label>
          First UTC date (inclusive)
          <input
            type="date"
            min="2025-01-01"
            max="2025-01-31"
            required
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          Before UTC date (exclusive)
          <input
            type="date"
            min="2025-01-02"
            max="2025-02-01"
            required
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
        <div className="wide">
          {m.panel}
          <button
            type="submit"
            disabled={m.busy || !symbols.length || start >= end}
          >
            {m.busy ? "Submitting…" : "Submit ingestion"}
          </button>
        </div>
      </form>
    </>
  );
}
export function IngestionDetail({ id }: { id: string }) {
  const r = useResource(
    `/v1/ingestion/submissions/${id}`,
    (d) => !d.complete && d.jobs?.some((j: Data) => active(j)),
  );
  return (
    <>
      <PageTitle eyebrow="DURABLE DAILY JOBS" title="Ingestion submission" />
      <ErrorBox>{r.error}</ErrorBox>
      <p className="exact">{id}</p>
      {r.data && (
        <>
          <section className="stat-grid">
            <div>
              <span>Total daily jobs</span>
              <strong>{r.data.total}</strong>
            </div>
            <div>
              <span>Succeeded</span>
              <strong>{r.data.succeeded}</strong>
            </div>
            <div>
              <span>Failed</span>
              <strong>{r.data.failed}</strong>
            </div>
            <div>
              <span>Completion</span>
              <strong>
                {r.data.complete ? "Complete" : "Partial / pending"}
              </strong>
            </div>
          </section>
          <WorkerNotice kind="ingestion" />
          <section className="panel">
            {r.data.jobs.map((job: Data) => (
              <details key={job.job_id}>
                <summary>
                  {job.symbol} · {job.trade_date} <Tag value={job.state} /> ·
                  attempts {job.attempt_count}/3
                </summary>
                <DataView data={job} />
              </details>
            ))}
          </section>
          <Provenance data={r.data.submission} />
        </>
      )}
      <Refresh r={r} />
    </>
  );
}
export function ResearchDetail({ id }: { id: string }) {
  const info = useResource(`/v1/research/runs/${id}`, active);
  const done = info.data?.state === "succeeded";
  const summary = useResource(done ? `/v1/research/runs/${id}/summary` : null);
  const results = useResource(done ? `/v1/research/runs/${id}/results` : null);
  return (
    <>
      <PageTitle eyebrow="PINNED RESEARCH RUN" title="Numerical results">
        {info.data && <Tag value={info.data.state} />}
      </PageTitle>
      <p className="exact" data-testid="run-id">
        {id}
      </p>
      <ErrorBox>{info.error}</ErrorBox>
      {info.data && (
        <>
          <section className="panel">
            <h2>{label(info.data.spec?.workflow ?? "Research")}</h2>
            <DataView
              data={{
                evaluation_start: info.data.spec?.start,
                evaluation_end_exclusive: info.data.spec?.end,
                history_start: info.data.spec?.history_start,
                interval: "5m",
                attempt_count: info.data.attempt_count,
              }}
            />
            {!done && <WorkerNotice kind="research" />}
            {info.data.error && <ErrorBox>{info.data.error}</ErrorBox>}
          </section>
          {done && (
            <>
              <section className="panel" data-testid="numerical-summary">
                <div className="toolbar">
                  <h2>Verified numerical summary</h2>
                  {summary.cache && <Tag value={`cache ${summary.cache}`} />}
                </div>
                <p className="muted">
                  Exact backend values · descriptive statistics · ratios are not
                  percent-scaled · Sharpe proxy is unannualized
                </p>
                <ErrorBox>{summary.error}</ErrorBox>
                {summary.data && <DataView data={summary.data} />}
              </section>
              <BarsChart spec={info.data.spec} results={results.data} />
              <section className="panel">
                <h2>Complete numerical results</h2>
                <ErrorBox>{results.error}</ErrorBox>
                {results.data && <DataView data={results.data} />}
              </section>
              <Memo run={id} />
            </>
          )}
          <Provenance
            data={info.data}
            title="Pinned specification, attempts and provenance"
          />
        </>
      )}
      <Refresh r={info} />
    </>
  );
}
function Memo({ run }: { run: string }) {
  const r = useResource(`/v1/research/runs/${run}/memo`, active);
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
  return (
    <section className="panel memo" data-testid="memo-panel">
      <div className="toolbar">
        <h2>Generated research memo</h2>
        {r.data && <Tag value={r.data.status ?? r.data.state} />}
      </div>
      <p className="muted">
        Supplemental generated content. Numerical results remain available
        independently.
      </p>
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
      {r.data && ["pending", "running"].includes(r.data.status) && (
        <WorkerNotice kind="shared inference" />
      )}
      {r.data?.error && <ErrorBox>{r.data.error}</ErrorBox>}
      {!r.data && r.error.toLowerCase().includes("not found") && (
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void enqueue()}
        >
          Enqueue historical memo
        </button>
      )}
      {r.data && (
        <Provenance data={r.data} title="Memo provenance and hashes" />
      )}
      <Refresh r={r} />
    </section>
  );
}
export function CopilotForm() {
  const [text, setText] = useState("");
  const [versions, setVersions] = useState(() =>
    selectedVersions()
      .map((v) => v.dataset_version_id)
      .join("\n"),
  );
  const [error, setError] = useState("");
  const m = useMutation("copilot.new", "/v1/copilot/requests", (d) =>
    navigate(`/copilot/${d.request_id}`),
  );
  return (
    <>
      <PageTitle
        eyebrow="CONSTRAINED LOCAL INTERPRETATION"
        title="Ask the copilot"
      />
      <p className="intro">
        Describe one supported January research request. Specify UTC evaluation,
        history, metrics and assets. Ambiguity can require clarification;
        validated requests submit through the same research service.
      </p>
      <form
        className="panel form-grid"
        onSubmit={(e) => {
          e.preventDefault();
          try {
            setError("");
            m.submit(
              JSON.stringify({
                schema: "copilot-request-v1",
                text,
                dataset_versions: versionIDs(versions),
                context: {},
              }),
            );
          } catch (e) {
            setError((e as Error).message);
          }
        }}
      >
        <label className="wide">
          Research request
          <textarea
            required
            rows={6}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe your research question…"
          />
          <small>
            At most 8,192 UTF-8 bytes; no trading recommendations or forecasts.
          </small>
        </label>
        <VersionInput value={versions} onChange={setVersions} />
        <div className="wide">
          <ErrorBox>{error}</ErrorBox>
          {m.panel}
          <button
            disabled={m.busy || new TextEncoder().encode(text).length > 8192}
            type="submit"
          >
            {m.busy ? "Submitting…" : "Submit copilot request"}
          </button>
        </div>
      </form>
    </>
  );
}
export function CopilotDetail({ id }: { id: string }) {
  const r = useResource(`/v1/copilot/requests/${id}`, active);
  const [text, setText] = useState("");
  const revision = r.data?.current_revision ?? 0;
  const m = useMutation(
    `copilot.answer.${id}.${revision}`,
    `/v1/copilot/requests/${id}/clarifications`,
    () => {
      setText("");
      r.refresh();
    },
  );
  useEffect(() => {
    window.addEventListener("marketlab-conflict", r.refresh);
    return () => window.removeEventListener("marketlab-conflict", r.refresh);
  }, [r.refresh]);
  return (
    <>
      <PageTitle
        eyebrow="INTERPRETATION AND CLARIFICATION"
        title="Copilot request"
      >
        {r.data && <Tag value={r.data.outcome ?? r.data.state} />}
      </PageTitle>
      <p className="exact">{id}</p>
      <ErrorBox>{r.error}</ErrorBox>
      {r.data && (
        <>
          <section className="panel">
            <p>{r.data.body?.text}</p>
            <p>Revision {revision} of at most 5 clarification rounds</p>
            {active(r.data) && <WorkerNotice kind="shared inference" />}
            {r.data.outcome === "submitted" && (
              <p className="notice">
                Validated interpretation submitted a queued numerical run.{" "}
                <a href={`#/runs/${r.data.run_id}`}>Open research run</a>
              </p>
            )}
            {r.data.revisions?.map((item: Data) => (
              <article className="revision" key={item.revision}>
                <h2>
                  Revision {item.revision}{" "}
                  <Tag value={item.outcome ?? item.state} />
                </h2>
                {item.questions && <DataView data={item.questions} />}
                <p>
                  Attempts {item.attempt_count}/3 · reserved model calls{" "}
                  {item.model_calls}/2
                </p>
                {item.error && <ErrorBox>{item.error}</ErrorBox>}
              </article>
            ))}
          </section>
          {r.data.outcome === "needs_clarification" && Number(revision) < 5 && (
            <form
              className="panel"
              onSubmit={(e) => {
                e.preventDefault();
                m.submit(
                  JSON.stringify({
                    schema: "copilot-answer-v1",
                    expected_revision: Number(revision),
                    text,
                    context: {},
                  }),
                );
              }}
            >
              <label>
                Clarification answer
                <textarea
                  required
                  rows={4}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              </label>
              {m.panel}
              <button type="submit" disabled={m.busy}>
                Submit clarification
              </button>
              <button type="button" className="secondary" onClick={r.refresh}>
                Refresh current revision
              </button>
              <p className="muted">
                A stale revision is rejected. Refresh before answering again;
                existing answers are never overwritten.
              </p>
            </form>
          )}
          <Provenance
            data={r.data}
            title="Request, revisions, exact versions and provenance"
          />
        </>
      )}
      <Refresh r={r} />
    </>
  );
}
