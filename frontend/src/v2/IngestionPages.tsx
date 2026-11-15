import { Fragment, useEffect, useState } from "react";
import type { Data } from "../client";
import { ErrorBox, PageTitle, Provenance, Tag } from "../components";
import { navigate } from "../hooks";
import { ShortId, WorkerHint } from "../ui";
import { mutate } from "./api";
import { ExecutionHistory, ExecutionHost, ExecutionWorker } from "./Execution";
import { useAction, useV2 } from "./hooks";
import { daysBetween } from "./state";
import {
  Facts,
  Field,
  InstrumentPages,
  InstrumentPill,
  Status,
  instrumentMap,
  seriesOf,
  useInstruments,
} from "./parts";

export function Official() {
  const instruments = useInstruments();
  const [ids, setIds] = useState<string[]>([]);
  const [first, setFirst] = useState("");
  const [before, setBefore] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const action = useAction();
  useEffect(() => {
    if (
      instruments.data &&
      !instruments.cursor &&
      instruments.rows.filter((v) => v.enabled).length === 1 &&
      !instruments.data.next_cursor
    )
      setIds((v) =>
        v.length ? v : [instruments.rows.find((r) => r.enabled)!.instrument_id],
      );
  }, [instruments.data]);
  let count: number | null = null;
  try {
    count = daysBetween(first, before) * ids.length;
  } catch {
    /* no estimate until dates valid */
  }
  return (
    <>
      <PageTitle title="Ingestion" />
      <div className="narrow">
        <form
          className="panel"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              const partitions = daysBetween(first, before) * ids.length;
              if (!ids.length || ids.length > 2 || partitions > 62)
                throw new Error(
                  "Choose 1 or 2 instruments and at most 62 daily jobs.",
                );
              if (
                Date.parse(`${before}T00:00:00Z`) >
                Math.floor(Date.now() / 86400000) * 86400000
              )
                throw new Error("Choose days that have already ended (UTC).");
              if (!confirmed)
                throw new Error("Confirm the request before submitting.");
              const result = await mutate(
                "official-submit",
                "/v2/ingestion/submissions",
                {
                  schema: "daily-ingestion-v2",
                  adapter: "binance_daily",
                  instrument_ids: [...ids].sort(),
                  from_date: first,
                  before_date: before,
                },
              );
              navigate(`/v2/submissions/${result.id ?? result.submission_id}`);
            });
          }}
        >
          <fieldset>
            <legend>
              Instruments <span className="note">Up to 2</span>
            </legend>
            <div className="checklist">
              {instruments.rows
                .filter((v) => v.enabled)
                .map((row) => (
                  <label key={row.instrument_id} className="check">
                    <input
                      type="checkbox"
                      checked={ids.includes(row.instrument_id)}
                      onChange={(e) => {
                        setConfirmed(false);
                        setIds(
                          e.target.checked
                            ? [...ids, row.instrument_id]
                            : ids.filter((v) => v !== row.instrument_id),
                        );
                      }}
                    />
                    <InstrumentPill
                      small
                      id={row.instrument_id}
                      instrument={row}
                    />
                    <span className="muted">{row.display_name}</span>
                  </label>
                ))}
            </div>
          </fieldset>
          <div className="fields">
            <Field
              title="From"
              value={first}
              type="date"
              change={(v) => {
                setFirst(v);
                setConfirmed(false);
              }}
            />
            <Field
              title="Before"
              value={before}
              type="date"
              change={(v) => {
                setBefore(v);
                setConfirmed(false);
              }}
            />
          </div>
          {count !== null && <Status>{count} of 62 daily jobs</Status>}
          <label className="check">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            Confirm these instruments and dates
          </label>
          <div className="actions">
            <button disabled={action.busy}>Start ingestion</button>
          </div>
        </form>
        <InstrumentPages result={instruments} />
        <ErrorBox>{action.error}</ErrorBox>
      </div>
    </>
  );
}
export function Submission({ id }: { id: string }) {
  const status = useV2(`/v2/ingestion/submissions/${id}`, true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const instruments = useInstruments();
  const action = useAction();
  const jobs: Data[] = status.data?.jobs ?? [];
  const map = instrumentMap(instruments.rows);
  const ids = jobs.map((job) => job.instrument_id as string);
  const count = (...states: string[]) =>
    jobs.filter((job) => states.includes(job.state)).length;
  const active = count("queued", "running", "retry_wait");
  return (
    <>
      <PageTitle
        title="Ingestion"
        meta={<ShortId value={id} label="submission ID" />}
      >
        <div className="title-actions">
          {jobs.some((job) => job.result_version) && (
            <a className="button secondary" href="#/v2/catalog">
              Open catalog
            </a>
          )}
          <button type="button" className="secondary" onClick={status.refresh}>
            Refresh
          </button>
        </div>
      </PageTitle>
      <ErrorBox>{status.error || action.error}</ErrorBox>
      {status.data && (
        <>
          <Facts
            items={[
              ["Jobs", jobs.length],
              ["Succeeded", count("succeeded")],
              ["Failed", count("failed")],
              ["Active", active],
            ]}
          />
          {active > 0 && (
            <WorkerHint kind="ingestion_v2" id={id} jobs={jobs.length} />
          )}
          <div className="table-wrap">
            <table>
              <caption>Ingestion jobs</caption>
              <thead>
                <tr>
                  <th>Instrument</th>
                  <th>Day</th>
                  <th>State</th>
                  <th>Host</th>
                  <th>Worker</th>
                  <th className="num">Attempts</th>
                  <th>Version</th>
                  <th>
                    <span className="sr-only">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <Fragment key={job.job_id}>
                    <tr key={job.job_id}>
                      <td>
                        <InstrumentPill
                          small
                          id={job.instrument_id}
                          instrument={map.get(job.instrument_id)}
                          series={seriesOf(ids, job.instrument_id)}
                        />
                      </td>
                      <td>{job.trade_date}</td>
                      <td>
                        <div role={job.error_code ? "alert" : undefined}>
                          <Tag value={job.state} />
                          {job.error_code && (
                            <span className="cell-error">{job.error_code}</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <ExecutionHost
                          execution={job.execution_status}
                          state={job.state}
                        />
                      </td>
                      <td>
                        <ExecutionWorker
                          execution={job.execution_status}
                          state={job.state}
                        />
                      </td>
                      <td className="num">
                        <button
                          type="button"
                          className="secondary"
                          aria-label={`Attempts for ${job.instrument_id} ${job.trade_date}`}
                          aria-expanded={expanded === job.job_id}
                          onClick={() =>
                            setExpanded(
                              expanded === job.job_id ? null : job.job_id,
                            )
                          }
                        >
                          {job.attempt_count}
                        </button>
                      </td>
                      <td>
                        {job.result_version && (
                          <ShortId
                            value={job.result_version}
                            label="published version"
                          />
                        )}
                      </td>
                      <td>
                        {!["succeeded", "failed", "cancelled"].includes(
                          job.state,
                        ) && (
                          <button
                            type="button"
                            className="secondary"
                            disabled={action.busy || job.cancel_requested}
                            onClick={() =>
                              void action.run(async () => {
                                await mutate(
                                  `job-cancel-${job.job_id}-${job.revision}`,
                                  `/v2/jobs/${job.job_id}/cancel`,
                                  { expected_revision: job.revision },
                                );
                                status.refresh();
                              })
                            }
                          >
                            Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                    {expanded === job.job_id && (
                      <tr className="ingestion-execution">
                        <td colSpan={8}>
                          <ExecutionHistory
                            execution={job.execution_status}
                            state={job.state}
                            title={`Execution · ${job.trade_date}`}
                            level={3}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <Provenance
            title="Attempt history"
            data={Object.fromEntries(
              jobs.map((job) => [
                `${job.instrument_id} ${job.trade_date}`,
                job.attempts,
              ]),
            )}
          />
        </>
      )}
    </>
  );
}
