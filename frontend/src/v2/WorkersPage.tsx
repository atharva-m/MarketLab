import { useState } from "react";
import { ErrorBox, PageTitle, Tag, keyLabel } from "../components";
import { ShortId } from "../ui";
import { ExecutionTime, HostIdentity } from "./Execution";
import { useV2 } from "./hooks";
import { Pager, Status, idPath, query } from "./parts";

type Work = {
  kind: string;
  identity: string;
  parent_id: string | null;
  revision?: number | null;
  attempt_number: number;
};

type Worker = {
  instance_id: string;
  host_id: string;
  host_label: string;
  state: string;
  heartbeat_at: string;
  fresh: boolean;
  registered_at: string;
  capabilities: string[];
  active_work: Work[];
  active_work_truncated: boolean;
};

function workPath(work: Work) {
  const id = idPath(work.identity);
  const parent = work.parent_id && idPath(work.parent_id);
  switch (work.kind) {
    case "research":
      return `#/v2/runs/${id}`;
    case "memo":
      return `#/v2/runs/${id}`;
    case "ingestion":
      return parent ? `#/v2/submissions/${parent}` : null;
    case "copilot":
      return parent ? `#/v2/copilot/${parent}` : null;
    default:
      return null;
  }
}

function ActiveWork({ worker }: { worker: Worker }) {
  if (!worker.active_work.length) return <span className="muted">None</span>;
  return (
    <>
      <ul className="worker-work">
        {worker.active_work.map((work) => {
          const href = workPath(work);
          const name = `${keyLabel(work.kind)} attempt ${work.attempt_number}`;
          return (
            <li key={`${work.kind}:${work.identity}:${work.attempt_number}`}>
              {href ? <a href={href}>{name}</a> : name}{" "}
              <ShortId value={work.identity} label={`${work.kind} job ID`} />
              {work.revision != null && (
                <span> · Revision {work.revision}</span>
              )}
            </li>
          );
        })}
      </ul>
      {worker.active_work_truncated && (
        <span className="muted">More active work</span>
      )}
    </>
  );
}

export function Workers({ id }: { id?: string }) {
  const [cursors, setCursors] = useState([""]);
  const cursor = cursors.at(-1);
  const state = useV2(
    `/v2/workers?${query(id ? { instance_id: id } : { limit: "25", cursor })}`,
    "always",
  );
  const workers = (state.data?.items ?? []) as Worker[];
  const next = state.data?.next_cursor as string | null | undefined;
  return (
    <>
      <PageTitle
        title={id ? "Worker" : "Workers"}
        meta={id && <ShortId value={id} label="worker ID" />}
      >
        <div className="title-actions">
          {id && (
            <a className="button secondary" href="#/v2/workers">
              All workers
            </a>
          )}
          <button type="button" className="secondary" onClick={state.refresh}>
            Refresh
          </button>
        </div>
      </PageTitle>
      <ErrorBox>{state.error}</ErrorBox>
      {state.busy && !state.data && <Status>Loading workers…</Status>}
      {state.data && (
        <section className="section worker-inventory">
          {state.data.registry_available === false ? (
            <Status>The worker registry is unavailable on this stack.</Status>
          ) : !workers.length ? (
            <Status>
              {id ? "Worker not found." : "No registered workers on this page."}
            </Status>
          ) : (
            <>
              <p className="muted">
                Last checked <ExecutionTime value={state.data.observed_at} />.
                Active work reflects valid job leases.
              </p>
              <div className="table-wrap">
                <table>
                  <caption>Registered workers</caption>
                  <thead>
                    <tr>
                      <th>Host</th>
                      <th>Worker</th>
                      <th>Reported state</th>
                      <th>Heartbeat</th>
                      <th>Capabilities</th>
                      <th>Active work</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workers.map((worker) => (
                      <tr key={worker.instance_id}>
                        <td>
                          <HostIdentity
                            label={worker.host_label}
                            id={worker.host_id}
                          />
                        </td>
                        <td>
                          <ShortId
                            value={worker.instance_id}
                            label="worker ID"
                          />
                          <span className="execution-note muted">
                            Registered{" "}
                            <ExecutionTime value={worker.registered_at} />
                          </span>
                        </td>
                        <td>
                          <Tag value={worker.state} />
                        </td>
                        <td>
                          <span>
                            {worker.state === "stopped"
                              ? "Last reported"
                              : worker.fresh
                                ? "Fresh"
                                : "Stale"}
                          </span>
                          <span className="execution-note">
                            <ExecutionTime value={worker.heartbeat_at} />
                          </span>
                        </td>
                        <td>
                          {worker.capabilities.map(keyLabel).join(", ") ||
                            "None"}
                        </td>
                        <td>
                          <ActiveWork worker={worker} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {!id && (cursors.length > 1 || next) && (
            <Pager
              page={cursors.length - 1}
              pages={cursors.length + (next ? 1 : 0)}
              label="worker"
              text={`Page ${cursors.length}`}
              onPage={(page) =>
                setCursors((stack) =>
                  page < stack.length - 1
                    ? stack.slice(0, page + 1)
                    : next
                      ? [...stack, next]
                      : stack,
                )
              }
            />
          )}
        </section>
      )}
    </>
  );
}
