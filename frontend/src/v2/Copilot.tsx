import { useState } from "react";
import type { Data } from "../client";
import { ErrorBox, Provenance, Tag } from "../components";
import { navigate } from "../hooks";
import { ShortId } from "../ui";
import { freshOperation, mutate } from "./api";
import { useAction, useV2 } from "./hooks";
import { selected } from "./state";
import {
  copilotBody,
  emptyContext,
  memoParagraphs,
  requestId,
  turnBody,
  type ContextForm,
} from "./copilotState";

function Context({
  form,
  change,
  ids,
}: {
  form: ContextForm;
  change: (form: ContextForm) => void;
  ids: string[];
}) {
  return (
    <details>
      <summary>Optional explicit structured context</summary>
      <p>
        Blank fields stay unspecified. Structured values are part of your
        request and must agree with your text.
      </p>
      <div className="v2-form">
        <label>
          Context workflow
          <select
            value={form.workflow}
            onChange={(e) => change({ ...form, workflow: e.target.value })}
          >
            <option value="">Unspecified</option>
            <option value="market_profile">Market profile</option>
            <option value="cross_asset">Cross asset</option>
            <option value="volatility_cluster">Volatility cluster</option>
          </select>
        </label>
        <label>
          Context interval
          <select
            value={form.interval}
            onChange={(e) => change({ ...form, interval: e.target.value })}
          >
            <option value="">Unspecified</option>
            <option value="5m">5 minutes</option>
          </select>
        </label>
        {(
          [
            ["history_start", "Context history start UTC (inclusive)"],
            ["start", "Context evaluation start UTC (inclusive)"],
            ["end", "Context evaluation end UTC (exclusive)"],
          ] as const
        ).map(([name, label]) => (
          <label key={name}>
            {label}
            <input
              value={form[name]}
              placeholder="YYYY-MM-DDTHH:mm:00Z"
              onChange={(e) => change({ ...form, [name]: e.target.value })}
            />
          </label>
        ))}
        <fieldset>
          <legend>Context instruments (optional subset)</legend>
          {ids.map((id) => (
            <label className="v2-check" key={id}>
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
              {id}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Context metrics (optional)</legend>
          {[
            "profile",
            "correlation",
            "close_change_difference",
            "clusters",
          ].map((metric) => (
            <label className="v2-check" key={metric}>
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
              {metric}
            </label>
          ))}
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
      className="panel v2-form"
      onSubmit={(e) => {
        e.preventDefault();
        void action.run(async () => {
          if (!requestId.test(id))
            throw new Error("Enter a valid copilot request UUID.");
          navigate(`/v2/copilot/${id}`);
        });
      }}
    >
      <h3>Recover a durable request</h3>
      <label>
        Copilot request ID
        <input required value={id} onChange={(e) => setId(e.target.value)} />
      </label>
      <button>Open copilot request</button>
      <ErrorBox>{action.error}</ErrorBox>
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
  return (
    <>
      <h2>Selected-catalog copilot</h2>
      <p>
        Interpret an explicit request against your pinned Binance spot versions.
        Numerical execution uses the same validated service as manual research.
      </p>
      {id ? (
        <CopilotStatus key={id} id={id} />
      ) : (
        <CopilotCreate available={available} />
      )}
      <p>
        <a href="#/v2/research/new">Open manual numerical research</a>
      </p>
    </>
  );
}
function CopilotCreate({ available }: { available: boolean }) {
  const [pins] = useState(selected);
  const ids = [...new Set(pins.map((row) => row.instrument_id))].sort();
  const [text, setText] = useState("");
  const [form, setForm] = useState(emptyContext);
  const [confirmed, setConfirmed] = useState(false);
  const action = useAction();
  return (
    <>
      <section className="panel">
        <h3>Explicit selected context · {pins.length}/62 daily versions</h3>
        {pins.length ? (
          <ul className="v2-pins">
            {pins.map((row) => (
              <li key={row.dataset_version_id}>
                {row.instrument_id} · {row.trade_date} ·{" "}
                <ShortId
                  value={row.dataset_version_id}
                  label="copilot pinned version"
                />
              </li>
            ))}
          </ul>
        ) : (
          <p>
            Pin registered versions, including required history, before creating
            a request.
          </p>
        )}
        <a href="#/v2/catalog">Choose catalog versions</a>
      </section>
      {!available && (
        <p role="status">
          Copilot creation is unavailable on this stack. Existing requests
          remain readable.
        </p>
      )}
      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            if (!available)
              throw new Error("Copilot creation is unavailable on this stack.");
            const body = copilotBody(text, form, pins);
            if (!confirmed)
              throw new Error(
                "Confirm the exact selected versions before submitting.",
              );
            const result = await mutate(
              "copilot-create",
              "/v2/copilot/requests",
              body,
            );
            if (!requestId.test(result.request_id))
              throw new Error(
                "The API returned an invalid request identity. Retry the same request to recover its outcome.",
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
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <p>
          {new TextEncoder().encode(text).length}/8,192 UTF-8 bytes. The server
          also enforces the unchanged 6,000-byte aggregate inference budget
          across turns and context.
        </p>
        <Context form={form} change={setForm} ids={ids} />
        <label className="v2-check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I confirm these exact selected versions. This selection stays frozen
          for all clarification answers.
        </label>
        <ErrorBox>{action.error}</ErrorBox>
        <button
          disabled={action.busy || !available || !pins.length || ids.length > 2}
        >
          Submit selected-context request
        </button>
        {action.error && (
          <p>
            Retry an unchanged request to recover its original operation;
            changing its text or context creates a new operation.
          </p>
        )}
      </form>
      <Recovery />
    </>
  );
}
function CopilotStatus({ id }: { id: string }) {
  const status = useV2(`/v2/copilot/requests/${id}`, true);
  const info = status.data;
  return (
    <section className="panel">
      <ShortId value={id} label="copilot request ID" />
      <p>Keep this request ID or URL to recover status after reloading.</p>
      <button type="button" className="secondary" onClick={status.refresh}>
        Refresh copilot status
      </button>
      <ErrorBox>{status.error}</ErrorBox>
      {status.busy && !info && <p role="status">Loading durable request…</p>}
      {info && (
        <>
          <p role="status">
            Revision {info.current_revision}/5 · <Tag value={info.state} /> ·{" "}
            {info.outcome ?? "Awaiting interpretation"}
          </p>
          {(info.revisions ?? []).map((revision: Data) => (
            <section key={revision.revision}>
              <h3>Revision {revision.revision}</h3>
              <p>
                {revision.outcome ?? revision.state} · reserved model calls:{" "}
                {revision.model_calls ?? 0}/2
              </p>
              <ErrorBox>{revision.error_code}</ErrorBox>
              {Array.isArray(revision.questions) && (
                <ul>
                  {revision.questions.map((question: Data, i: number) => (
                    <li key={i}>
                      {question.field}: {question.question}
                    </li>
                  ))}
                </ul>
              )}
              {revision.spec && (
                <Provenance
                  data={revision.spec}
                  title={`Validated numerical spec for revision ${revision.revision}`}
                />
              )}
            </section>
          ))}
          {info.run_id && requestId.test(info.run_id) && (
            <p>
              <a href={`#/v2/runs/${info.run_id}`}>
                Open linked numerical result
              </a>
            </p>
          )}
          {info.outcome === "needs_clarification" &&
            !info.run_id &&
            info.current_revision < 5 &&
            info.state === "succeeded" && (
              <Answer
                key={info.current_revision}
                info={info}
                refresh={status.refresh}
              />
            )}
          {info.outcome === "needs_clarification" &&
            info.current_revision === 5 && (
              <p>
                Five answers have been accepted. This request has reached its
                clarification limit; create a fresh request to continue.
              </p>
            )}
          <Provenance
            data={info.snapshot}
            title="Frozen selected catalog context"
          />
          <p>
            <a
              href="#/v2/copilot/new"
              onClick={() => freshOperation("copilot-create")}
            >
              Create a fresh selected-context request
            </a>
          </p>
        </>
      )}
    </section>
  );
}
function Answer({ info, refresh }: { info: Data; refresh: () => void }) {
  const [text, setText] = useState("");
  const [form, setForm] = useState(emptyContext);
  const [accepted, setAccepted] = useState(false);
  const action = useAction();
  const ids = Object.values(info.snapshot?.instruments ?? {}).map(
    (v) => (v as Data).instrument_id as string,
  );
  if (accepted)
    return (
      <p role="status">
        Answer accepted. Refresh status to follow the next durable revision.
      </p>
    );
  return (
    <form
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
      <h3>Answer clarification · {info.current_revision + 1}/5</h3>
      <label>
        Clarification answer
        <textarea
          required
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      <Context form={form} change={setForm} ids={ids} />
      <ErrorBox>{action.error}</ErrorBox>
      {action.error && (
        <p>
          Refresh durable status before retrying. An unchanged answer reuses its
          operation key; a stale revision cannot create more work.
        </p>
      )}
      <button disabled={action.busy}>Submit clarification answer</button>
    </form>
  );
}

export function Memo({ id, available }: { id: string; available: boolean }) {
  const status = useV2(`/v2/research/runs/${id}/memo`, true);
  const action = useAction();
  const info = status.data;
  const missing = status.errorStatus === 404;
  const paragraphs = memoParagraphs(info?.memo);
  return (
    <section className="panel" aria-labelledby="v2-memo-title">
      <h3 id="v2-memo-title">Supplemental grounded memo</h3>
      <p>
        Numerical results and charts remain usable independently of memo
        availability.
      </p>
      <button type="button" className="secondary" onClick={status.refresh}>
        Refresh memo status
      </button>
      <ErrorBox>{action.error || (!missing && status.error)}</ErrorBox>
      {status.busy && !info && <p role="status">Checking memo status…</p>}
      {missing && (
        <>
          <p>
            No supplemental memo has been queued for this verified numerical
            result.
          </p>
          <button
            type="button"
            disabled={action.busy || !available}
            onClick={() =>
              void action.run(async () => {
                await mutate(
                  `memo-enqueue-${id}`,
                  `/v2/research/runs/${id}/memo`,
                  { schema: "memo-request-v2" },
                );
                status.refresh();
              })
            }
          >
            Queue supplemental memo
          </button>
          {!available && <p>Memo enqueue is unavailable on this stack.</p>}
        </>
      )}
      {info && (
        <>
          <p role="status">
            <Tag value={info.state} /> · reserved model calls:{" "}
            {info.model_calls}/2
          </p>
          <ErrorBox>{info.error_code}</ErrorBox>
          {info.state === "failed" && (
            <p>
              This terminal memo failure remains readable. The numerical result
              is retained.
            </p>
          )}
          {info.state === "succeeded" &&
            (paragraphs ? (
              <div className="v2-memo-text">
                {paragraphs.map((paragraph, i) => (
                  <p className="v2-wrap" key={i}>
                    {paragraph}
                  </p>
                ))}
              </div>
            ) : (
              <ErrorBox>
                The memo response does not contain exactly three readable
                paragraphs. Refresh verified status.
              </ErrorBox>
            ))}
          <Provenance
            data={{
              numerical_manifest_sha256: info.numerical_manifest_sha256,
              summary_sha256: info.summary_sha256,
              manifest: info.manifest,
            }}
            title="Memo grounding and manifest"
          />
        </>
      )}
    </section>
  );
}
