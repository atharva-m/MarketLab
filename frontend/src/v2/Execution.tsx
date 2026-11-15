import { useId } from "react";
import { Tag, keyLabel } from "../components";
import { ShortId } from "../ui";
import { SectionHead, idPath } from "./parts";

export type Attempt = {
  attempt_number: number;
  worker_instance_id: string | null;
  host_id: string | null;
  host_label: string | null;
  started_at: string;
  ended_at: string | null;
  outcome: string;
  error_code: string | null;
  fencing_token: number | string;
  lease_valid: boolean | null;
};

export type ExecutionStatus = {
  observed_at: string;
  current_attempt: number | null;
  successful_attempt: number | null;
  attempts: Attempt[];
};

export function ExecutionTime({ value }: { value?: string | null }) {
  const instant = value ? new Date(value) : null;
  if (!instant || !Number.isFinite(instant.getTime()))
    return <span className="muted">—</span>;
  return (
    <time className="execution-time" dateTime={value ?? undefined}>
      {instant.toISOString().slice(0, 19).replace("T", " ")} UTC
    </time>
  );
}

function elapsed(attempt: Attempt, observedAt: string) {
  const end = attempt.ended_at ?? observedAt;
  const ms = Date.parse(end) - Date.parse(attempt.started_at);
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return "<1 s";
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  if (!minutes) return `${seconds} s`;
  return `${minutes}m ${seconds % 60}s`;
}

export function WorkerIdentity({ id }: { id: string }) {
  return (
    <span className="execution-worker">
      <ShortId value={id} label="worker ID" />
      <a href={`#/v2/workers/${idPath(id)}`} aria-label={`View worker ${id}`}>
        View
      </a>
    </span>
  );
}

export function HostIdentity({
  label,
  id,
}: {
  label: string | null | undefined;
  id: string | null | undefined;
}) {
  if (label) return <span title={id ?? undefined}>{label}</span>;
  if (id) return <ShortId value={id} label="host ID" />;
  return <span className="muted">Not recorded</span>;
}

export function executionOwner(
  execution: ExecutionStatus | undefined,
  state: string,
) {
  const attempts = execution?.attempts ?? [];
  const latest = attempts.at(-1);
  const owned = execution?.current_attempt ?? execution?.successful_attempt;
  const attempt =
    owned != null
      ? attempts.find((row) => row.attempt_number === owned)
      : ["failed", "cancelled"].includes(state) || latest?.lease_valid === false
        ? latest
        : undefined;
  const assignment =
    state === "queued" || state === "retry_wait"
      ? "Unassigned"
      : "Not recorded";
  const attribution = attempt
    ? execution?.current_attempt === attempt.attempt_number
      ? "Current worker"
      : execution?.successful_attempt === attempt.attempt_number
        ? "Successful worker"
        : "Last worker"
    : "Worker";
  return { attempt, assignment, attribution };
}

export function ExecutionHost({
  execution,
  state,
}: {
  execution?: ExecutionStatus;
  state: string;
}) {
  const { attempt, assignment } = executionOwner(execution, state);
  return attempt ? (
    <HostIdentity label={attempt.host_label} id={attempt.host_id} />
  ) : (
    <span className="muted">{assignment}</span>
  );
}

export function ExecutionWorker({
  execution,
  state,
}: {
  execution?: ExecutionStatus;
  state: string;
}) {
  const { attempt, assignment, attribution } = executionOwner(execution, state);
  return attempt?.worker_instance_id ? (
    <span>
      <WorkerIdentity id={attempt.worker_instance_id} />
      <span className="execution-note muted">{attribution}</span>
    </span>
  ) : (
    <span className="muted">{attempt ? "Not recorded" : assignment}</span>
  );
}

function transition(
  before: Attempt | undefined,
  after: Attempt,
  successful: boolean,
) {
  if (!before?.host_id || !after.host_id) return null;
  const from = before.host_label ?? "the previous host";
  const to = after.host_label ?? "another host";
  if (before.host_id === after.host_id) return "Retry on the same host";
  if (before.outcome === "expired" && successful)
    return `Recovered on ${to} after the lease expired on ${from}`;
  if (before.outcome === "expired")
    return `Claimed by ${to} after the lease expired on ${from}`;
  return `Retry moved from ${from} to ${to}`;
}

export function ExecutionHistory({
  execution,
  state,
  title = "Execution",
  level = 2,
}: {
  execution?: ExecutionStatus;
  state: string;
  title?: string;
  level?: 2 | 3;
}) {
  const id = useId();
  const attempts = execution?.attempts ?? [];
  return (
    <section className="section execution" aria-labelledby={id}>
      <SectionHead id={id} title={title} level={level} />
      {execution && (
        <p className="muted">
          Last checked <ExecutionTime value={execution.observed_at} />.
        </p>
      )}
      {!attempts.length ? (
        <p className="muted">
          {!execution
            ? "Execution history unavailable."
            : state === "queued" || state === "retry_wait"
              ? "Unassigned. Waiting for a worker."
              : "No worker attempts recorded."}
        </p>
      ) : (
        <>
          {(state === "queued" || state === "retry_wait") && (
            <p className="muted">Unassigned. Waiting for a worker.</p>
          )}
          {attempts.at(-1)?.lease_valid === false && (
            <p className="notice">
              No worker holds a valid lease for this job.
            </p>
          )}
          <div className="table-wrap">
            <table>
              <caption>Worker attempts</caption>
              <thead>
                <tr>
                  <th>Attempt</th>
                  <th>Host</th>
                  <th>Worker</th>
                  <th>Started</th>
                  <th>Duration</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {attempts.map((row, i) => {
                  const successful =
                    row.attempt_number === execution?.successful_attempt;
                  const current =
                    row.attempt_number === execution?.current_attempt;
                  const note = transition(attempts[i - 1], row, successful);
                  return (
                    <tr key={row.attempt_number}>
                      <th scope="row">{row.attempt_number}</th>
                      <td>
                        <HostIdentity label={row.host_label} id={row.host_id} />
                      </td>
                      <td>
                        {row.worker_instance_id ? (
                          <WorkerIdentity id={row.worker_instance_id} />
                        ) : (
                          <span className="muted">Not recorded</span>
                        )}
                      </td>
                      <td>
                        <ExecutionTime value={row.started_at} />
                      </td>
                      <td>{elapsed(row, execution?.observed_at ?? "")}</td>
                      <td>
                        {row.outcome === "expired" ? (
                          "Lease expired"
                        ) : (
                          <Tag value={row.outcome} />
                        )}
                        {row.lease_valid === false && (
                          <span className="execution-note">No valid lease</span>
                        )}
                        {current && (
                          <span className="execution-note">Current claim</span>
                        )}
                        {successful && (
                          <span className="execution-note">
                            Successful attempt
                          </span>
                        )}
                        {note && <span className="execution-note">{note}</span>}
                        {row.error_code && (
                          <span className="cell-error">
                            {keyLabel(row.error_code)}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <details className="provenance">
            <summary>Attempt details</summary>
            <dl className="kv">
              {attempts.map((row) => (
                <div key={row.attempt_number}>
                  <dt>Attempt {row.attempt_number}</dt>
                  <dd>
                    Fence <code>{row.fencing_token}</code>
                    {" · Ended "}
                    <ExecutionTime value={row.ended_at} />
                    {row.error_code && (
                      <>
                        {" · "}
                        <code>{row.error_code}</code>
                      </>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        </>
      )}
    </section>
  );
}
