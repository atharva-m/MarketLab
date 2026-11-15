import { useState } from "react";
import type { Data } from "../client";
import {
  ErrorBox,
  PageTitle,
  Provenance,
  Tag,
  label as humanise,
} from "../components";
import { navigate } from "../hooks";
import { ShortId } from "../ui";
import { freshOperation, mutate, type Instrument } from "./api";
import { useAction, useV2 } from "./hooks";
import { ExecutionHistory } from "./Execution";
import {
  Count,
  Facts,
  InstrumentPill,
  PinTable,
  SectionHead,
  Status,
  instrumentMap,
  seriesOf,
  useInstruments,
} from "./parts";
import { selected } from "./state";
import {
  copilotBody,
  emptyContext,
  requestId,
  turnBody,
  type ContextForm,
} from "./copilotState";

const name = (value: string) => {
  const text = humanise(value);
  return text.charAt(0).toUpperCase() + text.slice(1);
};

function Context({
  form,
  change,
  ids,
  instruments,
}: {
  form: ContextForm;
  change: (form: ContextForm) => void;
  ids: string[];
  instruments?: Map<string, Instrument>;
}) {
  return (
    <details>
      <summary>
        Structured context <span className="note">Optional</span>
      </summary>
      <div className="section">
        <div className="fields">
          <label>
            Workflow
            <select
              value={form.workflow}
              onChange={(e) => change({ ...form, workflow: e.target.value })}
            >
              <option value="">Any</option>
              <option value="market_profile">Market profile</option>
              <option value="cross_asset">Cross-asset comparison</option>
              <option value="volatility_cluster">Volatility clusters</option>
            </select>
          </label>
          <label>
            Interval
            <select
              value={form.interval}
              onChange={(e) => change({ ...form, interval: e.target.value })}
            >
              <option value="">Any</option>
              <option value="5m">5 minutes</option>
            </select>
          </label>
          {(
            [
              ["history_start", "History start"],
              ["start", "Evaluation start"],
              ["end", "Evaluation end"],
            ] as const
          ).map(([field, title]) => (
            <label key={field}>
              {title}
              <input
                value={form[field]}
                placeholder="2025-03-01T00:00:00Z"
                onChange={(e) => change({ ...form, [field]: e.target.value })}
              />
            </label>
          ))}
        </div>
        <fieldset>
          <legend>Instruments</legend>
          <div className="checklist">
            {ids.map((id) => (
              <label className="check" key={id}>
                <input
                  type="checkbox"
                  checked={form.instrument_ids.includes(id)}
                  onChange={(e) =>
                    change({
                      ...form,
                      instrument_ids: e.target.checked
                        ? [...form.instrument_ids, id]
                        : form.instrument_ids.filter((v) => v !== id),
                    })
                  }
                />
                <InstrumentPill
                  small
                  id={id}
                  instrument={instruments?.get(id)}
                  series={seriesOf(ids, id)}
                />
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>Metrics</legend>
          <div className="checklist">
            {[
              "profile",
              "correlation",
              "close_change_difference",
              "clusters",
            ].map((metric) => (
              <label className="check" key={metric}>
                <input
                  type="checkbox"
                  checked={form.metrics.includes(metric)}
                  onChange={(e) =>
                    change({
                      ...form,
                      metrics: e.target.checked
                        ? [...form.metrics, metric]
                        : form.metrics.filter((v) => v !== metric),
                    })
                  }
                />
                {name(metric)}
              </label>
            ))}
          </div>
        </fieldset>
      </div>
    </details>
  );
}

function Recovery() {
  const [id, setId] = useState(() => {
    try {
      return localStorage.getItem("marketlab.v2.copilot.last") ?? "";
    } catch {
      return "";
    }
  });
  const action = useAction();
  return (
    <form
      className="panel"
      onSubmit={(e) => {
        e.preventDefault();
        void action.run(async () => {
          if (!requestId.test(id)) throw new Error("Enter a valid request ID.");
          navigate(`/v2/copilot/${id}`);
        });
      }}
    >
      <SectionHead title="Open a request" />
      <label>
        Copilot request ID
        <input required value={id} onChange={(e) => setId(e.target.value)} />
      </label>
      <ErrorBox>{action.error}</ErrorBox>
      <div className="actions">
        <button className="secondary">Open</button>
      </div>
    </form>
  );
}

export function Copilot({
  id,
  available,
}: {
  id?: string;
  available: boolean;
}) {
  return id ? (
    <CopilotStatus key={id} id={id} />
  ) : (
    <CopilotCreate available={available} />
  );
}
function CopilotCreate({ available }: { available: boolean }) {
  const [pins] = useState(selected);
  const ids = [...new Set(pins.map((row) => row.instrument_id))].sort();
  const [text, setText] = useState("");
  const [form, setForm] = useState(emptyContext);
  const [confirmed, setConfirmed] = useState(false);
  const action = useAction();
  const instruments = instrumentMap(useInstruments().rows);
  return (
    <>
      <PageTitle title="Copilot">
        <a className="button secondary" href="#/v2/research/new">
          Manual research
        </a>
      </PageTitle>
      <div className="split roomy">
        <div className="grow section">
          {!available && (
            <section className="notice" role="status">
              Copilot is unavailable. Existing requests can still be opened.
            </section>
          )}
          <form
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                if (!available) throw new Error("Copilot is unavailable.");
                const body = copilotBody(text, form, pins);
                if (!confirmed)
                  throw new Error("Confirm the versions before submitting.");
                const result = await mutate(
                  "copilot-create",
                  "/v2/copilot/requests",
                  body,
                );
                if (!requestId.test(result.request_id))
                  throw new Error(
                    "The response was invalid. Submit again to recover the request.",
                  );
                try {
                  localStorage.setItem(
                    "marketlab.v2.copilot.last",
                    result.request_id,
                  );
                } catch {
                  /* URL remains recoverable */
                }
                navigate(`/v2/copilot/${result.request_id}`);
              });
            }}
          >
            <label>
              Research request
              <textarea
                required
                rows={6}
                spellCheck={false}
                placeholder="Describe the research you want…"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <span className="counter">
              {new TextEncoder().encode(text).length} of 8,192 bytes
            </span>
            <Context
              form={form}
              change={setForm}
              ids={ids}
              instruments={instruments}
            />
            <label className="check">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              Confirm these versions. They stay fixed for follow-up answers.
            </label>
            <ErrorBox>{action.error}</ErrorBox>
            <div className="actions">
              <button
                disabled={
                  action.busy || !available || !pins.length || ids.length > 2
                }
              >
                Ask copilot
              </button>
            </div>
          </form>
        </div>
        <div className="side">
          <section className="panel">
            <SectionHead title="Pinned versions">
              <Count value={pins.length} max={62} testId="pin-count" />
            </SectionHead>
            {pins.length ? (
              <PinTable rows={pins} instruments={instruments} />
            ) : (
              <p className="muted">Pin versions in the catalog first.</p>
            )}
            <div className="actions">
              <a className="button secondary" href="#/v2/catalog">
                Browse catalog
              </a>
            </div>
          </section>
          <Recovery />
        </div>
      </div>
    </>
  );
}
function CopilotStatus({ id }: { id: string }) {
  const status = useV2(`/v2/copilot/requests/${id}`, true);
  const info = status.data;
  const instruments = new Map<string, Instrument>(
    Object.values(info?.snapshot?.instruments ?? {}).map((v) => [
      (v as Data).instrument_id as string,
      v as Instrument,
    ]),
  );
  return (
    <>
      <PageTitle
        title="Copilot"
        meta={<ShortId value={id} label="copilot request ID" />}
      >
        <div className="title-actions">
          {info && <Tag value={info.outcome ?? info.state} />}
          <a
            className="button secondary"
            href="#/v2/copilot/new"
            onClick={() => freshOperation("copilot-create")}
          >
            New request
          </a>
          <button type="button" className="secondary" onClick={status.refresh}>
            Refresh
          </button>
        </div>
      </PageTitle>
      <ErrorBox>{status.error}</ErrorBox>
      {status.busy && !info && <Status>Loading…</Status>}
      {info && (
        <>
          <div role="status">
            <Facts
              items={[
                ["State", <Tag key="state" value={info.state} />],
                [
                  "Outcome",
                  info.outcome ? name(String(info.outcome)) : "Pending",
                ],
                ["Revision", `${info.current_revision} of 5`],
              ]}
            />
          </div>
          {info.run_id && requestId.test(info.run_id) && (
            <section className="notice">
              <p>Run queued.</p>
              <div className="actions">
                <a className="button" href={`#/v2/runs/${info.run_id}`}>
                  Open run
                </a>
              </div>
            </section>
          )}
          {(info.revisions ?? []).map((revision: Data) => (
            <article className="revision" key={revision.revision}>
              <h2>
                Revision {revision.revision}
                <Tag value={revision.outcome ?? revision.state} />
                <span className="muted">
                  Model calls {revision.model_calls ?? 0} of 2
                </span>
              </h2>
              <ErrorBox>{revision.error_code}</ErrorBox>
              {Array.isArray(revision.questions) &&
                revision.questions.length > 0 && (
                  <dl className="kv">
                    {revision.questions.map((question: Data, i: number) => (
                      <div key={i}>
                        <dt>{name(String(question.field))}</dt>
                        <dd>{question.question}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              {revision.spec && (
                <Provenance data={revision.spec} title="Spec" />
              )}
              <ExecutionHistory
                execution={revision.execution_status}
                state={revision.state}
                level={3}
              />
            </article>
          ))}
          {info.outcome === "needs_clarification" &&
            !info.run_id &&
            info.current_revision < 5 &&
            info.state === "succeeded" && (
              <Answer
                key={info.current_revision}
                info={info}
                instruments={instruments}
                refresh={status.refresh}
              />
            )}
          {info.outcome === "needs_clarification" &&
            info.current_revision === 5 && (
              <p className="notice">
                Clarification limit reached. Start a new request to continue.
              </p>
            )}
          <Provenance data={info.snapshot} title="Pinned context" />
        </>
      )}
    </>
  );
}
function Answer({
  info,
  instruments,
  refresh,
}: {
  info: Data;
  instruments: Map<string, Instrument>;
  refresh: () => void;
}) {
  const [text, setText] = useState("");
  const [form, setForm] = useState(emptyContext);
  const [accepted, setAccepted] = useState(false);
  const action = useAction();
  const ids = Object.values(info.snapshot?.instruments ?? {}).map(
    (v) => (v as Data).instrument_id as string,
  );
  if (accepted) return <Status>Answer sent.</Status>;
  return (
    <form
      className="panel"
      onSubmit={(e) => {
        e.preventDefault();
        void action.run(async () => {
          await mutate(
            `copilot-answer-${info.request_id}-${info.current_revision}`,
            `/v2/copilot/requests/${info.request_id}/clarifications`,
            {
              schema: "copilot-answer-v2",
              expected_revision: info.current_revision,
              ...turnBody(text, form, ids),
            },
          );
          setAccepted(true);
          refresh();
        });
      }}
    >
      <SectionHead title="Answer clarification">
        <Count
          value={info.current_revision + 1}
          max={5}
          testId="answer-round"
        />
      </SectionHead>
      <label>
        Clarification answer
        <textarea
          required
          rows={4}
          spellCheck={false}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      <Context
        form={form}
        change={setForm}
        ids={ids}
        instruments={instruments}
      />
      <ErrorBox>{action.error}</ErrorBox>
      <div className="actions">
        <button disabled={action.busy}>Send answer</button>
      </div>
    </form>
  );
}
