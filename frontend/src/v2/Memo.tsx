import { ErrorBox, Provenance, Tag } from "../components";
import { WorkerHint } from "../ui";
import { mutate } from "./api";
import { memoParagraphs } from "./copilotState";
import { ExecutionHistory } from "./Execution";
import { useAction, useV2 } from "./hooks";
import { Status } from "./parts";

export function Memo({ id, available }: { id: string; available: boolean }) {
  const status = useV2(`/v2/research/runs/${id}/memo`, true);
  const action = useAction();
  const info = status.data;
  const missing = status.errorStatus === 404;
  const paragraphs = memoParagraphs(info?.memo);
  const waiting = ["queued", "running", "retry_wait"].includes(info?.state);
  return (
    <section className="memo" aria-labelledby="v2-memo-title">
      <div className="toolbar">
        <div className="toolbar-group">
          <h2 id="v2-memo-title">Memo</h2>
          {info && <Tag value={info.state} />}
        </div>
        <button type="button" className="secondary" onClick={status.refresh}>
          Refresh
        </button>
      </div>
      <ErrorBox>{action.error || (!missing && status.error)}</ErrorBox>
      {status.busy && !info && <Status>Loading…</Status>}
      {missing && (
        <>
          <p className="muted">No memo yet.</p>
          <div className="actions">
            <button
              type="button"
              className="secondary"
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
              Queue memo
            </button>
          </div>
          {!available && <p className="muted">Memos are unavailable.</p>}
        </>
      )}
      {info && (
        <>
          <ErrorBox>{info.error_code}</ErrorBox>
          {info.state === "succeeded" &&
            (paragraphs ? (
              <div className="v2-memo-text memo-content">
                {paragraphs.map((paragraph, i) => (
                  <p key={i}>{paragraph}</p>
                ))}
              </div>
            ) : (
              <ErrorBox>This memo could not be displayed.</ErrorBox>
            ))}
          {waiting && (
            <WorkerHint kind="inference" running={info.state === "running"} />
          )}
          <p className="muted">Model calls {info.model_calls} of 2</p>
          <ExecutionHistory
            execution={info.execution_status}
            state={info.state}
            title="Memo execution"
            level={3}
          />
          <Provenance
            data={{
              numerical_manifest_sha256: info.numerical_manifest_sha256,
              summary_sha256: info.summary_sha256,
              manifest: info.manifest,
            }}
            title="Memo provenance"
          />
        </>
      )}
    </section>
  );
}
