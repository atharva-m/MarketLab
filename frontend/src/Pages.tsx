import { useEffect, useState, type FormEvent } from "react";
import {
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
} from "./components";
import { ShortId, WorkerHint } from "./ui";
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
      <PageTitle title="New research run" />
      <p className="intro">
        Pin exact versions and an evaluation window. The server checks coverage
        and warm-up before it accepts the run.
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
            <option value="market_profile">Market profile</option>
            <option value="cross_asset">Cross-asset comparison</option>
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
            <option value="BTCUSDT">BTC/USDT</option>
            <option value="ETHUSDT">ETH/USDT</option>
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
            Profiles and cross-asset runs need 12 prior bars; clusters need 300.
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
          Five-minute bars. Clusters use volatility quantile 0.9, volume
          multiple 2 and at least 2 bars. Missing bars are never filled.
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
            <p role="status" className="muted">
              Validation can take several minutes. Keep this page open; the run
              is queued once it is accepted.
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
      <PageTitle title="New ingestion" />
      <p className="intro">
        Request official daily trade archives. A worker downloads, verifies and
        publishes each day as an immutable version.
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
        <p className="muted">
          Up to 62 daily jobs per submission. Each day succeeds or fails on its
          own.
        </p>
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
      <PageTitle
        title="Ingestion submission"
        meta={<ShortId value={id} label="submission ID" />}
      />
      <ErrorBox>{r.error}</ErrorBox>
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
          {!r.data.complete && r.data.jobs?.some((j: Data) => active(j)) && (
            <WorkerHint
              kind="ingestion"
              id={id}
              jobs={r.data.total}
              since={r.data.submission?.created_at}
            />
          )}
          <section className="panel">
            {r.data.jobs.map((job: Data) => (
              <details key={job.job_id}>
                <summary>
                  {job.symbol} · {job.trade_date} <Tag value={job.state} />{" "}
                  <span className="muted">
                    attempt {job.attempt_count} of 3
                  </span>
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
      <PageTitle title="Ask the copilot" />
      <p className="intro">
        Describe one research run in plain words: assets, UTC evaluation window,
        warm-up history and metrics. The copilot asks when something is unclear
        and submits the run once it validates.
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
            Up to 8,192 bytes. Forecasts and trading advice are out of scope.
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
        title="Copilot request"
        meta={<ShortId value={id} label="request ID" />}
      >
        {r.data && <Tag value={r.data.outcome ?? r.data.state} />}
      </PageTitle>
      <ErrorBox>{r.error}</ErrorBox>
      {r.data && (
        <>
          <section className="panel">
            <p>{r.data.body?.text}</p>
            <p>Revision {revision} of at most 5 clarification rounds</p>
            {active(r.data) && (
              <WorkerHint
                kind="copilot"
                id={id}
                running={r.data.state === "running"}
              />
            )}
            {r.data.outcome === "submitted" && (
              <p className="notice">
                The request validated and queued a research run.{" "}
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
                <p className="muted">
                  Attempt {item.attempt_count} of 3, model calls{" "}
                  {item.model_calls} of 2
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
                Answers apply to the current revision only. If the request
                changed, refresh before answering.
              </p>
            </form>
          )}
          <Provenance data={r.data} />
        </>
      )}
      <Refresh r={r} />
    </>
  );
}
