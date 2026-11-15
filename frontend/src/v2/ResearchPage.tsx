import { useEffect, useRef, useState } from "react";
import type { Data } from "../client";
import { DataView, ErrorBox, PageTitle } from "../components";
import { navigate } from "../hooks";
import {
  api,
  freshOperation,
  mutate,
  type Dataset,
  type Instrument,
} from "./api";
import { errorText, useAction } from "./hooks";
import {
  daysBetween,
  researchSpec,
  saveSelection,
  selected,
  suggestedWindow,
  utc,
} from "./state";
import {
  Count,
  Facts,
  Field,
  InstrumentPages,
  InstrumentPill,
  PinTable,
  SectionHead,
  Status,
  idPath,
  instrumentMap,
  query,
  seriesOf,
  useInstruments,
} from "./parts";

const WORKFLOWS: [string, string][] = [
  ["market_profile", "Market profile"],
  ["cross_asset", "Cross-asset comparison"],
  ["volatility_cluster", "Volatility clusters"],
];
const METRIC_NAMES: Record<string, string> = {
  profile: "Profile",
  correlation: "Correlation",
  close_change_difference: "Close change difference",
  clusters: "Clusters",
};

export function Research({ capabilities }: { capabilities: Data | null }) {
  const instruments = useInstruments();
  const [pins, setPins] = useState(selected);
  const [form, setForm] = useState<Data>(() => {
    try {
      return {
        workflow: "market_profile",
        instrument_ids: [...new Set(selected().map((v) => v.instrument_id))],
        history_start: "",
        start: "",
        end: "",
        metrics: ["profile"],
        ...JSON.parse(localStorage.getItem("marketlab.v2.research") ?? "{}"),
      };
    } catch {
      return {
        workflow: "market_profile",
        instrument_ids: [],
        history_start: "",
        start: "",
        end: "",
        metrics: ["profile"],
      };
    }
  });
  const [metadata, setMetadata] = useState<Instrument[]>([]);
  const [first, setFirst] = useState("");
  const [before, setBefore] = useState("");
  const [coverage, setCoverage] = useState<Data[]>([]);
  const coverageRequest = useRef<AbortController | null>(null);
  const coverageSignature = JSON.stringify([
    form.instrument_ids,
    form.workflow,
    first,
    before,
  ]);
  const coverageCurrent = useRef(coverageSignature);
  coverageCurrent.current = coverageSignature;
  useEffect(() => {
    coverageRequest.current?.abort();
    return () => coverageRequest.current?.abort();
  }, [coverageSignature]);
  const [confirmed, setConfirmed] = useState(false);
  const [pinText, setPinText] = useState("");
  const action = useAction();
  const [note, setNote] = useState("");
  const limits = capabilities?.limits ?? {};
  const change = (name: string, value: unknown) => {
    setForm((v) => ({ ...v, [name]: value }));
    setConfirmed(false);
    setNote("");
    if (name === "instrument_ids" || name === "workflow") setCoverage([]);
  };
  useEffect(() => {
    try {
      localStorage.setItem("marketlab.v2.research", JSON.stringify(form));
    } catch {
      /* in-memory selection remains */
    }
  }, [form]);
  useEffect(() => {
    if (
      instruments.data &&
      !instruments.cursor &&
      !form.instrument_ids.length &&
      instruments.rows.length === 1 &&
      !instruments.data.next_cursor
    )
      change("instrument_ids", [instruments.rows[0].instrument_id]);
  }, [instruments.data]);
  useEffect(() => {
    const own = new AbortController();
    const ids = form.instrument_ids as string[];
    if (ids.length > 2) return;
    Promise.all(
      ids.map((id) =>
        api(`/v2/instruments/${idPath(id)}`, { signal: own.signal }),
      ),
    ).then(
      (rows) => setMetadata(rows as Instrument[]),
      () => {
        if (!own.signal.aborted) setMetadata([]);
      },
    );
    return () => own.abort();
  }, [JSON.stringify(form.instrument_ids)]);
  const metrics =
    form.workflow === "cross_asset"
      ? ["profile", "correlation", "close_change_difference"]
      : form.workflow === "volatility_cluster"
        ? ["profile", "clusters"]
        : ["profile"];
  let buckets = "—";
  try {
    const n =
      ((utc(form.end) - utc(form.history_start)) / 300000) *
      form.instrument_ids.length;
    buckets = `${n} of ${limits.research_buckets ?? 17856}`;
  } catch {
    /* incomplete input */
  }
  const byId = instrumentMap(instruments.rows);
  const pinIds = pins.map((v) => v.instrument_id);
  return (
    <>
      <PageTitle title="New research">
        <a className="button secondary" href="#/v2/copilot/new">
          Ask copilot
        </a>
      </PageTitle>
      <div className="split roomy">
        <div className="grow">
          <form
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                if (!capabilities) throw new Error("Limits are still loading.");
                if (!confirmed)
                  throw new Error("Confirm the request before submitting.");
                const spec = researchSpec(form, pins, metadata, limits);
                const result = await mutate(
                  "research-create",
                  "/v2/research/runs",
                  spec,
                );
                navigate(`/v2/runs/${result.id}`);
              });
            }}
          >
            <label>
              Workflow
              <select
                value={form.workflow}
                onChange={(e) => {
                  change("workflow", e.target.value);
                  change("metrics", ["profile"]);
                }}
              >
                {WORKFLOWS.map(([value, name]) => (
                  <option key={value} value={value}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <fieldset>
              <legend>
                Instruments
                <span className="note">
                  {form.workflow === "cross_asset"
                    ? "Pick two with the same quote asset"
                    : "Pick one"}
                </span>
              </legend>
              <div className="checklist">
                {instruments.rows.map((row) => (
                  <label className="check" key={row.instrument_id}>
                    <input
                      type="checkbox"
                      checked={form.instrument_ids.includes(row.instrument_id)}
                      onChange={(e) =>
                        change(
                          "instrument_ids",
                          e.target.checked
                            ? [...form.instrument_ids, row.instrument_id]
                            : form.instrument_ids.filter(
                                (v: string) => v !== row.instrument_id,
                              ),
                        )
                      }
                    />
                    <InstrumentPill
                      small
                      id={row.instrument_id}
                      instrument={row}
                    />
                    <span className="muted">
                      {row.display_name}
                      {row.enabled ? "" : " (read only)"}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>
                Window
                <span className="note">UTC, on five-minute boundaries</span>
              </legend>
              <div className="fields lead">
                <Field
                  title="History start"
                  value={form.history_start}
                  change={(v) => change("history_start", v)}
                  placeholder="2025-03-01T00:00:00Z"
                />
                <Field
                  title="Evaluation start"
                  value={form.start}
                  change={(v) => change("start", v)}
                  placeholder="2025-03-01T00:00:00Z"
                />
                <Field
                  title="Evaluation end"
                  value={form.end}
                  change={(v) => change("end", v)}
                  placeholder="2025-03-01T00:00:00Z"
                />
              </div>
            </fieldset>
            <fieldset>
              <legend>Metrics</legend>
              <div className="checklist">
                {metrics.map((metric) => (
                  <label className="check" key={metric}>
                    <input
                      type="checkbox"
                      checked={form.metrics.includes(metric)}
                      onChange={(e) =>
                        change(
                          "metrics",
                          e.target.checked
                            ? [...form.metrics, metric]
                            : form.metrics.filter((v: string) => v !== metric),
                        )
                      }
                    />
                    {METRIC_NAMES[metric] ?? metric}
                  </label>
                ))}
              </div>
            </fieldset>
            {form.workflow === "volatility_cluster" && (
              <Facts
                items={[
                  ["Volatility quantile", "0.9"],
                  ["Volume multiple", "2"],
                  ["Minimum bars", "2"],
                  ["Warm-up", "300 bars"],
                ]}
              />
            )}
            <div role="status">
              <Facts
                items={[
                  ["Buckets", buckets],
                  ["Versions", `${pins.length} of ${limits.partitions ?? 62}`],
                ]}
              />
            </div>
            <label className="check">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              Confirm these versions and time range
            </label>
            <div className="actions">
              <button disabled={action.busy || !capabilities}>
                Run research
              </button>
              <button
                type="button"
                className="secondary"
                disabled={action.busy}
                onClick={() => {
                  freshOperation("research-create");
                  setConfirmed(false);
                  setNote("Ready to submit as a new run.");
                }}
              >
                New request key
              </button>
            </div>
          </form>
          <InstrumentPages result={instruments} />
          <ErrorBox>{action.error}</ErrorBox>
          {note && <Status>{note}</Status>}
        </div>
        <div className="side">
          <section className="panel">
            <SectionHead title="Pinned versions">
              <Count value={pins.length} max={62} testId="pin-count" />
            </SectionHead>
            <PinTable rows={pins} instruments={byId} />
            <div className="actions">
              <a className="button secondary" href="#/v2/catalog">
                Browse catalog
              </a>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  saveSelection([]);
                  setPins([]);
                  setConfirmed(false);
                }}
              >
                Clear
              </button>
            </div>
            <label>
              Add by version ID
              <textarea
                rows={3}
                placeholder="One 64-character ID per line"
                value={pinText}
                onChange={(e) => setPinText(e.target.value)}
              />
            </label>
            <div className="actions">
              <button
                type="button"
                className="secondary"
                disabled={action.busy}
                onClick={() =>
                  void action.run(async () => {
                    const ids = [
                      ...new Set(pinText.split(/[\s,]+/).filter(Boolean)),
                    ];
                    if (
                      !ids.length ||
                      ids.length + pins.length > 62 ||
                      ids.some((id) => !/^[a-f0-9]{64}$/.test(id))
                    )
                      throw new Error(
                        "Enter 64-character version IDs, at most 62 in total.",
                      );
                    const found = await Promise.all(
                      ids.map((id) => api(`/v2/datasets/${id}`)),
                    );
                    const additions = found.map((body, i) => {
                      const legacy = body.legacy_manifest;
                      return {
                        dataset_version_id: ids[i],
                        instrument_id:
                          body.instrument?.instrument_id ?? body.instrument_id,
                        trade_date:
                          body.identity?.trade_date ?? legacy?.trade_date,
                        row_count:
                          body.quality?.accepted_rows ??
                          legacy?.quality?.accepted_rows ??
                          "unknown",
                        contract: body.schema,
                      } as Dataset;
                    });
                    const rows = [...pins, ...additions];
                    saveSelection(rows);
                    setPins(rows);
                    setPinText("");
                    setConfirmed(false);
                  })
                }
              >
                Add
              </button>
            </div>
          </section>
          <section className="panel">
            <SectionHead title="Coverage" />
            <div className="fields">
              <Field
                title="Coverage from"
                type="date"
                value={first}
                change={(v) => {
                  setFirst(v);
                  setCoverage([]);
                }}
              />
              <Field
                title="Coverage before"
                type="date"
                value={before}
                change={(v) => {
                  setBefore(v);
                  setCoverage([]);
                }}
              />
            </div>
            <div className="actions">
              <button
                type="button"
                className="secondary"
                disabled={action.busy}
                onClick={() =>
                  void action.run(async () => {
                    const n = daysBetween(first, before);
                    if (
                      n > 62 ||
                      !form.instrument_ids.length ||
                      form.instrument_ids.length > 2
                    )
                      throw new Error(
                        "Choose 1 or 2 instruments and at most 62 days.",
                      );
                    const own = new AbortController();
                    coverageRequest.current?.abort();
                    coverageRequest.current = own;
                    const signature = coverageSignature;
                    const rows = await Promise.all(
                      form.instrument_ids.map((id: string) =>
                        api(
                          `/v2/coverage?${query({ instrument_id: id, from_date: first, before_date: before })}`,
                          { signal: own.signal },
                        ),
                      ),
                    );
                    if (
                      !own.signal.aborted &&
                      coverageCurrent.current === signature
                    )
                      setCoverage(rows);
                  })
                }
              >
                Load coverage
              </button>
              {!!coverage.length && (
                <button
                  type="button"
                  className="secondary"
                  disabled={action.busy}
                  onClick={() => {
                    const suggestion = suggestedWindow(
                      coverage,
                      form.workflow,
                      limits,
                    );
                    if (!suggestion) {
                      setNote(
                        "No single interval fits. Pin versions manually.",
                      );
                      return;
                    }
                    try {
                      saveSelection(suggestion.rows);
                      setPins(suggestion.rows);
                      setForm({
                        ...form,
                        history_start: suggestion.history_start,
                        start: suggestion.start,
                        end: suggestion.end,
                      });
                      setConfirmed(false);
                      setNote("Latest interval applied. Review and confirm.");
                    } catch (e) {
                      setNote(errorText(e));
                    }
                  }}
                >
                  Use latest interval
                </button>
              )}
            </div>
            {coverage.map((body) => (
              <details key={body.instrument_id}>
                <summary>
                  <InstrumentPill
                    small
                    id={body.instrument_id}
                    instrument={byId.get(body.instrument_id)}
                    series={seriesOf(pinIds, body.instrument_id)}
                  />{" "}
                  <span className="muted">{body.days?.length ?? 0} days</span>{" "}
                  {body.gaps.length ? (
                    <span style={{ color: "var(--warn)" }}>
                      {body.gaps.length} gaps
                    </span>
                  ) : (
                    <span className="muted">No gaps</span>
                  )}
                </summary>
                <DataView data={body} />
              </details>
            ))}
          </section>
        </div>
      </div>
    </>
  );
}
