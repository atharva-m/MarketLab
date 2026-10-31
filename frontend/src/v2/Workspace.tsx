import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import type { Data } from "../client";
import { DataView, ErrorBox, PageTitle, Provenance, Tag } from "../components";
import { navigate } from "../hooks";
import { ShortId } from "../ui";
import {
  api,
  freshOperation,
  hashFile,
  mutate,
  uploadFile,
  type Dataset,
  type Instrument,
  type Upload,
} from "./api";
import { errorText, useAction, useV2 } from "./hooks";
import {
  daysBetween,
  instrumentLabel,
  researchSpec,
  saveSelection,
  selected,
  suggestedWindow,
  utc,
} from "./state";
import "./workspace.css";

const query = (values: Record<string, string | undefined>) =>
  new URLSearchParams(
    Object.entries(values).filter((v): v is [string, string] => !!v[1]),
  ).toString();
const idPath = (value: string) => encodeURIComponent(value);
const links = [
  ["/v2/catalog", "Catalog"],
  ["/v2/research/new", "Research"],
  ["/v2/ingestion/new", "Official ingestion"],
  ["/v2/imports/new", "File import"],
  ["/v2/instruments", "Instruments"],
];
function Header({ route }: { route: string }) {
  return (
    <>
      <PageTitle title="Binance spot workspace" />
      <p className="intro">
        Registered instruments and dates · exact pinned datasets · local
        operator access
      </p>
      <nav className="v2-tabs" aria-label="Binance workspace navigation">
        {links.map(([href, label]) => (
          <a
            key={href}
            href={`#${href}`}
            aria-current={route === href ? "page" : undefined}
          >
            {label}
          </a>
        ))}
      </nav>
    </>
  );
}
function Field({
  title,
  value,
  change,
  type = "text",
  required = true,
  hint,
}: {
  title: string;
  value: string;
  change: (value: string) => void;
  type?: string;
  required?: boolean;
  hint?: string;
}) {
  return (
    <label>
      {title}
      <input
        aria-label={title}
        type={type}
        value={value}
        onChange={(e) => change(e.target.value)}
        required={required}
      />
      {hint && <small>{hint}</small>}
    </label>
  );
}
function Status({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="muted">
      {children}
    </p>
  );
}
function useInstruments() {
  const [cursor, setCursor] = useState("");
  const result = useV2(`/v2/instruments?${query({ limit: "100", cursor })}`);
  return {
    ...result,
    rows: (result.data?.items ?? []) as Instrument[],
    next: () => setCursor(result.data?.next_cursor ?? ""),
    first: () => setCursor(""),
    cursor,
  };
}
function InstrumentChoice({
  rows,
  value,
  onChange,
  enabledOnly = false,
  title = "Instrument",
}: {
  rows: Instrument[];
  value: string;
  onChange: (value: string) => void;
  enabledOnly?: boolean;
  title?: string;
}) {
  return (
    <label>
      {title}
      <select
        aria-label={title}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
      >
        <option value="">Choose a registered instrument</option>
        {value && !rows.some((v) => v.instrument_id === value) && (
          <option value={value}>
            {value} - preserved selection outside this page
          </option>
        )}
        {rows
          .filter((v) => !enabledOnly || v.enabled)
          .map((v) => (
            <option key={v.instrument_id} value={v.instrument_id}>
              {instrumentLabel(v)}
            </option>
          ))}
      </select>
    </label>
  );
}
function InstrumentPages({
  result,
}: {
  result: ReturnType<typeof useInstruments>;
}) {
  return (
    <>
      <ErrorBox>{result.error}</ErrorBox>
      {result.data?.next_cursor && (
        <button type="button" className="secondary" onClick={result.next}>
          Next instrument page
        </button>
      )}
      {result.cursor && (
        <button type="button" className="secondary" onClick={result.first}>
          First instrument page
        </button>
      )}
    </>
  );
}
function EmptyCatalog() {
  return (
    <section className="notice">
      <h2>No registered data in this view</h2>
      <p>
        Register verified Binance spot instrument metadata, then ingest an
        official daily archive or upload a Binance-origin canonical CSV/Parquet
        file. A successful upload becomes selectable only after durable
        publication.
      </p>
      <a href="#/v2/instruments">Manage instruments</a>
      {" · "}
      <a href="#/v2/ingestion/new">Ingest official data</a>
      {" · "}
      <a href="#/v2/imports/new">Import a canonical file</a>
    </section>
  );
}
export function V2Workspace({ route }: { route: string }) {
  const capabilities = useV2("/v2/capabilities");
  const parts = route.split("/").filter(Boolean);
  const [family, id] = parts.slice(1);
  let page: ReactNode;
  if (family === "research" && id === "new")
    page = <Research capabilities={capabilities.data} />;
  else if (family === "runs" && /^[a-f0-9-]{36}$/.test(id ?? ""))
    page = <Run key={id} id={id} />;
  else if (family === "ingestion") page = <Official />;
  else if (family === "submissions" && /^[a-f0-9-]{36}$/.test(id ?? ""))
    page = <Submission key={id} id={id} />;
  else if (family === "imports")
    page = <Import key={id ?? "new"} id={id !== "new" ? id : undefined} />;
  else if (family === "instruments") page = <Registry />;
  else page = <Catalog />;
  return (
    <div className="v2-workspace">
      <Header route={route} />
      <ErrorBox>{capabilities.error}</ErrorBox>
      {capabilities.data && (
        <details className="v2-capabilities">
          <summary>Effective workload and storage limits</summary>
          <p>
            Local stack limits; observed coverage does not prove a complete
            trading history.
          </p>
          <DataView data={capabilities.data.limits} />
          <p>Generalized copilot and memos are unavailable until Phase 5.</p>
        </details>
      )}
      {page}
    </div>
  );
}

function Catalog() {
  const instruments = useInstruments();
  const [filter, setFilter] = useState({
    instrument_id: "",
    from_date: "",
    before_date: "",
  });
  const [applied, setApplied] = useState<Record<string, string>>({});
  const [cursor, setCursor] = useState("");
  const catalog = useV2(
    `/v2/datasets?${query({ ...applied, limit: "25", cursor })}`,
  );
  const [pins, setPins] = useState(selected);
  const [error, setError] = useState("");
  const [inspect, setInspect] = useState("");
  const detail = useV2(inspect ? `/v2/datasets/${inspect}` : null);
  const rows = (catalog.data?.items ?? []) as Dataset[];
  const toggle = (row: Dataset, checked: boolean) => {
    try {
      const next = checked
        ? [...pins, row]
        : pins.filter((v) => v.dataset_version_id !== row.dataset_version_id);
      saveSelection(next);
      setPins(next);
      setError("");
    } catch (e) {
      setError(errorText(e));
    }
  };
  useEffect(() => {
    if (
      instruments.data &&
      !instruments.cursor &&
      instruments.rows.length === 1 &&
      !instruments.data.next_cursor
    )
      setFilter((v) =>
        v.instrument_id
          ? v
          : { ...v, instrument_id: instruments.rows[0].instrument_id },
      );
  }, [instruments.data]); // The response, not current selection, determines uniqueness.
  return (
    <>
      <h2>Registered datasets</h2>
      <p>
        Pin exactly one immutable alternative per instrument/day. Counts remain
        exact; all dates are UTC. Catalog pages reflect current committed data,
        not a frozen snapshot.
      </p>
      <form
        className="panel v2-form"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(filter);
          setCursor("");
        }}
      >
        <InstrumentChoice
          rows={instruments.rows}
          value={filter.instrument_id}
          onChange={(v) => setFilter({ ...filter, instrument_id: v })}
        />
        <Field
          title="From UTC date (inclusive)"
          type="date"
          value={filter.from_date}
          required={false}
          change={(v) => setFilter({ ...filter, from_date: v })}
        />
        <Field
          title="Before UTC date (exclusive)"
          type="date"
          value={filter.before_date}
          required={false}
          change={(v) => setFilter({ ...filter, before_date: v })}
        />
        <div className="actions">
          <button>Filter catalog</button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setFilter({ instrument_id: "", from_date: "", before_date: "" });
              setApplied({});
              setCursor("");
            }}
          >
            All registered data
          </button>
        </div>
      </form>
      <InstrumentPages result={instruments} />
      <ErrorBox>{catalog.error || error}</ErrorBox>
      {catalog.busy && <Status>Loading registered metadata…</Status>}
      {catalog.data && !rows.length && <EmptyCatalog />}
      {!!rows.length && (
        <div className="table-scroll">
          <table>
            <caption>Immutable daily versions</caption>
            <thead>
              <tr>
                <th>Pin</th>
                <th>Instrument / venue</th>
                <th>UTC day</th>
                <th>Rows</th>
                <th>Version</th>
                <th>Provenance</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.contract}/${row.dataset_version_id}`}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Pin ${row.instrument_id} ${row.trade_date} ${row.dataset_version_id}`}
                      checked={pins.some(
                        (v) => v.dataset_version_id === row.dataset_version_id,
                      )}
                      onChange={(e) => toggle(row, e.target.checked)}
                    />
                  </td>
                  <td>
                    {row.instrument_id}
                    <small className="v2-block">Binance spot</small>
                  </td>
                  <td>{row.trade_date}</td>
                  <td>{String(row.row_count)}</td>
                  <td>
                    <ShortId
                      value={row.dataset_version_id}
                      label="dataset version"
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setInspect(row.dataset_version_id)}
                    >
                      Inspect version
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="actions">
        <button
          type="button"
          className="secondary"
          onClick={() => catalog.refresh()}
        >
          Refresh catalog
        </button>
        {catalog.data?.next_cursor && (
          <button
            type="button"
            onClick={() => setCursor(catalog.data!.next_cursor)}
          >
            Next dataset page
          </button>
        )}
        {cursor && (
          <button
            type="button"
            className="secondary"
            onClick={() => setCursor("")}
          >
            First dataset page
          </button>
        )}
      </div>
      <section className="panel">
        <h3>Pinned selection · {pins.length}/62 daily versions</h3>
        {pins.length ? (
          <>
            <PinList rows={pins} />
            <div className="actions">
              <a href="#/v2/research/new">Research this selection</a>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  saveSelection([]);
                  setPins([]);
                }}
              >
                Clear selection
              </button>
            </div>
          </>
        ) : (
          <p>Select registered versions above, including required history.</p>
        )}
      </section>
      {inspect && (
        <section className="panel">
          <h3>Verified version detail</h3>
          <ErrorBox>{detail.error}</ErrorBox>
          {detail.data && <DataView data={detail.data} />}
        </section>
      )}
    </>
  );
}
function PinList({ rows }: { rows: Dataset[] }) {
  return (
    <ul className="v2-pins">
      {rows.map((row) => (
        <li key={row.dataset_version_id}>
          {row.instrument_id} · {row.trade_date} ·{" "}
          <ShortId value={row.dataset_version_id} label="pinned version" />
        </li>
      ))}
    </ul>
  );
}

function Registry() {
  const instruments = useInstruments();
  const action = useAction();
  const [form, setForm] = useState({
    source_symbol: "",
    base_asset: "",
    quote_asset: "",
    display_name: "",
  });
  const [verified, setVerified] = useState(false);
  const [editing, setEditing] = useState<Instrument | null>(null);
  const [display, setDisplay] = useState("");
  return (
    <>
      <h2>Binance spot instrument registry</h2>
      <p>
        Enter operator-verified Binance metadata explicitly. Asset codes are
        never inferred from a symbol. Semantic fields are immutable after
        registration.
      </p>
      <form
        className="panel v2-form"
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            if (!verified)
              throw new Error(
                "Verify the Binance instrument metadata before registering.",
              );
            await mutate("registry-create", "/v2/instruments", {
              venue_id: "binance",
              market: "spot",
              ...form,
              trade_id_order: "numeric",
              adapter: "binance_daily",
            });
            instruments.refresh();
          });
        }}
      >
        {Object.entries(form).map(([name, value]) => (
          <Field
            key={name}
            title={name.replaceAll("_", " ")}
            value={value}
            change={(v) => setForm({ ...form, [name]: v })}
          />
        ))}
        <label className="v2-check">
          <input
            type="checkbox"
            checked={verified}
            onChange={(e) => setVerified(e.target.checked)}
          />
          I verified this symbol and base/quote metadata against Binance spot
          records.
        </label>
        <button disabled={action.busy}>Register instrument</button>
      </form>
      <ErrorBox>{action.error || instruments.error}</ErrorBox>
      <div className="table-scroll">
        <table>
          <caption>Registered instruments</caption>
          <thead>
            <tr>
              <th>Identity and assets</th>
              <th>State</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {instruments.rows.map((row) => (
              <tr key={row.instrument_id}>
                <td>
                  {instrumentLabel(row)}
                  <small className="v2-block">{row.instrument_id}</small>
                </td>
                <td>
                  {row.enabled
                    ? "New ingestion enabled"
                    : "Retained reads/research only"}
                </td>
                <td>
                  <button
                    type="button"
                    className="secondary"
                    disabled={action.busy}
                    onClick={() => {
                      setEditing(row);
                      setDisplay(row.display_name);
                    }}
                  >
                    Edit display / enabled
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <InstrumentPages result={instruments} />
      {editing && (
        <form
          className="panel v2-form"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              await mutate(
                `registry-edit-${editing.instrument_id}-${editing.revision}`,
                `/v2/instruments/${idPath(editing.instrument_id)}`,
                {
                  display_name: display,
                  enabled: editing.enabled,
                  expected_revision: editing.revision,
                },
                "PATCH",
              );
              setEditing(null);
              instruments.refresh();
            });
          }}
        >
          <h3>{editing.instrument_id}</h3>
          <Field title="Display name" value={display} change={setDisplay} />
          <label className="v2-check">
            <input
              type="checkbox"
              checked={editing.enabled}
              onChange={(e) =>
                setEditing({ ...editing, enabled: e.target.checked })
              }
            />
            Enable new ingestion/imports
          </label>
          <button disabled={action.busy}>Save registry revision</button>
        </form>
      )}
    </>
  );
}

function Official() {
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
      <h2>Official daily archive ingestion</h2>
      <p>
        Completed UTC days only. Publication uses the existing checksum-verified
        durable pipeline. Missing research data is never downloaded
        automatically.
      </p>
      <form
        className="panel v2-form"
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            const partitions = daysBetween(first, before) * ids.length;
            if (!ids.length || ids.length > 2 || partitions > 62)
              throw new Error(
                "Choose 1–2 enabled instruments and at most 62 instrument/day partitions.",
              );
            if (
              Date.parse(`${before}T00:00:00Z`) >
              Math.floor(Date.now() / 86400000) * 86400000
            )
              throw new Error(
                "Official ingestion requires completed past UTC days.",
              );
            if (!confirmed)
              throw new Error("Confirm the bounded ingestion request.");
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
          <legend>Choose 1–2 enabled Binance instruments</legend>
          {instruments.rows
            .filter((v) => v.enabled)
            .map((row) => (
              <label key={row.instrument_id} className="v2-check">
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
                {instrumentLabel(row)}
              </label>
            ))}
        </fieldset>
        <Field
          title="From UTC date (inclusive)"
          value={first}
          type="date"
          change={(v) => {
            setFirst(v);
            setConfirmed(false);
          }}
        />
        <Field
          title="Before UTC date (exclusive)"
          value={before}
          type="date"
          change={(v) => {
            setBefore(v);
            setConfirmed(false);
          }}
        />
        <Status>Selected instruments: {ids.join(", ") || "none"}</Status>
        <Status>
          {count === null
            ? "Choose dates to estimate the workload."
            : `${count} instrument/day partitions · maximum 62`}
        </Status>
        <label className="v2-check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I confirm these instruments and UTC daily boundaries.
        </label>
        <button disabled={action.busy}>Submit official ingestion</button>
      </form>
      <InstrumentPages result={instruments} />
      <ErrorBox>{action.error}</ErrorBox>
    </>
  );
}
function Submission({ id }: { id: string }) {
  const status = useV2(`/v2/ingestion/submissions/${id}`, true);
  const action = useAction();
  return (
    <>
      <h2>Ingestion submission</h2>
      <ShortId value={id} label="submission ID" />
      <ErrorBox>{status.error || action.error}</ErrorBox>
      <button type="button" className="secondary" onClick={status.refresh}>
        Refresh status
      </button>
      {status.data && (
        <>
          <p>
            Each daily child is published independently after verification.
            Queued work requires the local ingestion worker.
          </p>
          {status.data.jobs?.map((job: Data) => (
            <section className="panel" key={job.job_id}>
              <h3>
                {job.instrument_id} · {job.trade_date}
              </h3>
              <Tag value={job.state} />
              <p>
                Attempts: {job.attempt_count} · revision {job.revision}
              </p>
              {job.error_code && <ErrorBox>{job.error_code}</ErrorBox>}
              {job.result_version && (
                <p>
                  Published version:{" "}
                  <ShortId
                    value={job.result_version}
                    label="published version"
                  />{" "}
                  · <a href="#/v2/catalog">Open catalog and pin this version</a>
                </p>
              )}
              {!["succeeded", "failed", "cancelled"].includes(job.state) && (
                <button
                  type="button"
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
                  Request cancellation
                </button>
              )}
              <Provenance data={job.attempts} title="Attempt history" />
            </section>
          ))}
        </>
      )}
    </>
  );
}

function Import({ id }: { id?: string }) {
  const instruments = useInstruments();
  const [importId, setImportId] = useState(id ?? "");
  const [lastImport] = useState(() => {
    try {
      const value = localStorage.getItem("marketlab.v2.lastImport") ?? "";
      return /^[a-f0-9-]{36}$/.test(value) ? value : "";
    } catch {
      return "";
    }
  });
  const status = useV2(importId ? `/v2/imports/${importId}` : null, true);
  const [form, setForm] = useState({
    instrument_id: "",
    trade_date: "",
    format: "csv",
    timestamp_encoding: "rfc3339_utc",
    source_name: "",
    source_reference: "",
  });
  const [file, setFile] = useState<File | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [stage, setStage] = useState("");
  const [bytes, setBytes] = useState(0);
  const [upload, setUpload] = useState<Upload | null>(null);
  const controller = useRef<AbortController | null>(null);
  const action = useAction();
  const cancellation = useAction();
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (
      instruments.data &&
      !instruments.cursor &&
      instruments.rows.filter((v) => v.enabled).length === 1 &&
      !instruments.data.next_cursor
    )
      setForm((v) =>
        v.instrument_id
          ? v
          : {
              ...v,
              instrument_id: instruments.rows.find((r) => r.enabled)!
                .instrument_id,
            },
      );
  }, [instruments.data]);
  const send = async (
    capability: Upload,
    source: File,
    signal: AbortSignal,
  ) => {
    setStage("Uploading bytes");
    setBytes(0);
    // Retire the in-memory capability at dispatch; any uncertain outcome is
    // resolved through durable status, never automatic byte retry.
    setUpload(null);
    await uploadFile(capability, source, setBytes, signal);
    setStage("Bytes verified; finalize to queue normalization.");
    status.refresh();
  };
  const selectedFile = () => {
    if (!file || file.size <= 0 || file.size > 4 * 1024 ** 3)
      throw new Error(
        "Select a nonempty canonical daily file of at most 4 GiB.",
      );
    return file;
  };
  const create = (event: FormEvent) => {
    event.preventDefault();
    void action.run(async () => {
      const source = selectedFile();
      if (!confirmed)
        throw new Error("Confirm the Binance origin and canonical format.");
      const own = new AbortController();
      controller.current = own;
      setStage("Hashing file");
      setBytes(0);
      try {
        const hash = await hashFile(source, setBytes, own.signal);
        const result = await mutate("import-create", "/v2/imports", {
          manifest: {
            schema: "canonical-trade-import-v1",
            ...form,
            quote_quantity_mode: "supplied",
            source_sha256: hash,
            source_reference: form.source_reference || null,
            coverage_claim: "observed_only",
          },
          content_length: source.size,
        });
        setImportId(result.id);
        try {
          localStorage.setItem("marketlab.v2.lastImport", result.id);
        } catch {
          /* status link remains in page */
        }
        const capability = result.upload as Upload;
        if (result.replayed) {
          const current = await api(`/v2/imports/${result.id}`, {
            signal: own.signal,
          });
          setUpload(
            current.state === "awaiting_upload" &&
              current.generation === capability.generation
              ? capability
              : null,
          );
          setStage(
            "Recovered the original operation and current durable status. No file bytes were retried automatically.",
          );
          status.refresh();
          return;
        }
        setUpload(capability);
        if (result.state === "awaiting_upload")
          await send(capability, source, own.signal);
        else {
          setStage("Recovered the original operation. Refresh durable status.");
          status.refresh();
        }
      } finally {
        controller.current = null;
      }
    });
  };
  const recoverUpload = () =>
    void action.run(async () => {
      const source = selectedFile();
      const info = status.data;
      if (!info) throw new Error("Refresh durable status first.");
      if (source.size !== Number(info.declared_bytes))
        throw new Error(
          "Reselect the original file with the exact declared size.",
        );
      const own = new AbortController();
      controller.current = own;
      try {
        setStage("Verifying reselected file");
        setBytes(0);
        const hash = await hashFile(source, setBytes, own.signal);
        if (hash !== info.source_sha256)
          throw new Error(
            "The reselected file does not match the import's original hash.",
          );
        let capability = upload;
        if (!capability) {
          const result = await mutate(
            `import-renew-${importId}-${info.revision}`,
            `/v2/imports/${importId}/upload`,
            { expected_revision: info.revision },
          );
          capability = result.upload;
          setUpload(capability);
          status.refresh();
        }
        if (!capability)
          throw new Error("The API returned no upload capability.");
        await send(capability, source, own.signal);
      } finally {
        controller.current = null;
      }
    });
  const info = status.data;
  const expiry = info?.generation_expires_at ?? info?.upload_expires_at;
  const mayRenew =
    info?.state === "upload_failed" ||
    (info?.state === "awaiting_upload" &&
      (!expiry || Date.parse(expiry) <= Date.now()));
  return (
    <>
      <h2>Canonical Binance file import</h2>
      <p>
        One Binance spot instrument and UTC day per file. Supply original
        numeric trade IDs, exact prices/quantities and quote quantities.
        Declared origin is not independent authenticity proof.
      </p>
      <details className="panel">
        <summary>Canonical format guidance</summary>
        <p>CSV header (UTF-8, exact column names):</p>
        <pre className="v2-wrap">
          source_trade_id,executed_at,price,quantity,quote_quantity,is_buyer_maker,is_best_match
        </pre>
        <p>
          Parquet uses string trade IDs, timestamp[us, UTC], decimal128(38,18)
          price/quantity/quote quantity and nullable boolean flags. No OHLCV
          data, arbitrary column mapping, implicit quote derivation, other
          exchanges or derivatives.
        </p>
        <p>
          Keep the original source and conversion evidence. Source references
          are inert provenance, never fetch destinations.
        </p>
      </details>
      {!importId && lastImport && (
        <p>
          <a href={`#/v2/imports/${lastImport}`}>
            Inspect the last saved import status
          </a>
        </p>
      )}
      {!importId && (
        <form className="panel v2-form" onSubmit={create}>
          <InstrumentChoice
            rows={instruments.rows}
            value={form.instrument_id}
            enabledOnly
            onChange={(v) => {
              setForm({ ...form, instrument_id: v });
              setConfirmed(false);
            }}
          />
          <Field
            title="Trade UTC date"
            type="date"
            value={form.trade_date}
            change={(v) => {
              setForm({ ...form, trade_date: v });
              setConfirmed(false);
            }}
          />
          <label>
            Canonical format
            <select
              value={form.format}
              onChange={(e) => {
                setForm({
                  ...form,
                  format: e.target.value,
                  timestamp_encoding:
                    e.target.value === "parquet"
                      ? "arrow_timestamp_us_utc"
                      : "rfc3339_utc",
                });
                setConfirmed(false);
              }}
            >
              <option value="csv">CSV</option>
              <option value="parquet">Parquet</option>
            </select>
          </label>
          <label>
            Timestamp encoding
            <select
              value={form.timestamp_encoding}
              onChange={(e) =>
                setForm({ ...form, timestamp_encoding: e.target.value })
              }
            >
              {(form.format === "parquet"
                ? ["arrow_timestamp_us_utc"]
                : [
                    "rfc3339_utc",
                    "unix_seconds",
                    "unix_milliseconds",
                    "unix_microseconds",
                  ]
              ).map((encoding) => (
                <option key={encoding}>{encoding}</option>
              ))}
            </select>
          </label>
          <Field
            title="Source name"
            value={form.source_name}
            change={(v) => setForm({ ...form, source_name: v })}
            hint="1–128 printable characters; retain conversion provenance."
          />
          <Field
            title="Source / conversion reference (optional)"
            value={form.source_reference}
            change={(v) => setForm({ ...form, source_reference: v })}
            required={false}
          />
          <label className="v2-check">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I confirm this is Binance-origin canonical trade data with supplied
            quote quantities and retained source/conversion evidence.
          </label>
          <label>
            Canonical daily file
            <input
              type="file"
              accept=".csv,.parquet"
              required
              disabled={action.busy}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setStage("");
              }}
            />
          </label>
          <button disabled={action.busy}>Hash and upload canonical file</button>
        </form>
      )}
      {!importId && <InstrumentPages result={instruments} />}
      <ErrorBox>{action.error || cancellation.error || status.error}</ErrorBox>
      {stage && (
        <Status>
          {stage}
          {file &&
            ` · ${bytes.toLocaleString("en-US")} / ${file.size.toLocaleString("en-US")} bytes`}
        </Status>
      )}
      {action.busy && (
        <button
          type="button"
          className="secondary"
          onClick={() => controller.current?.abort()}
        >
          Interrupt browser transfer / hashing
        </button>
      )}
      {importId && (
        <section className="panel">
          <h3>Durable import status</h3>
          <p>
            <a href={`#/v2/imports/${importId}`}>Bookmark status</a> ·{" "}
            <ShortId value={importId} label="import ID" />
          </p>
          <button type="button" className="secondary" onClick={status.refresh}>
            Refresh import status
          </button>
          {info && (
            <>
              <Tag value={info.state} />
              <p>
                Revision {info.revision} · received{" "}
                {String(info.received_bytes)} / {String(info.declared_bytes)}{" "}
                bytes
              </p>
              <p>
                Source SHA-256:{" "}
                <ShortId value={info.source_sha256} label="source SHA-256" />
              </p>
              {info.error && (
                <ErrorBox>{info.error.message ?? info.error.code}</ErrorBox>
              )}
              {["awaiting_upload", "upload_failed"].includes(info.state) && (
                <>
                  <p>
                    After interruption or refresh, reselect the original file.
                    Renewal is allowed only after a failed upload or unused
                    capability expiry. Old failed bytes remain charged.
                  </p>
                  <label>
                    Reselect original canonical file
                    <input
                      type="file"
                      accept=".csv,.parquet"
                      disabled={action.busy}
                      onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    />
                  </label>
                  {expiry && <p>Current generation expires: {expiry}</p>}
                  <button
                    type="button"
                    disabled={action.busy || (!upload && !mayRenew)}
                    onClick={recoverUpload}
                  >
                    {upload
                      ? "Upload selected generation"
                      : "Renew generation and upload original file"}
                  </button>
                </>
              )}
              {info.state === "uploaded" && (
                <>
                  <p>
                    Bytes are verified. Finalize once to queue normalization and
                    immutable publication.
                  </p>
                  <button
                    type="button"
                    disabled={action.busy}
                    onClick={() =>
                      void action.run(async () => {
                        await mutate(
                          `import-finalize-${importId}`,
                          `/v2/imports/${importId}/finalize`,
                          {
                            expected_revision: info.revision,
                            generation: info.generation,
                          },
                        );
                        status.refresh();
                      })
                    }
                  >
                    Finalize verified import
                  </button>
                </>
              )}
              {["queued", "running", "retry_wait"].includes(info.state) && (
                <p>
                  Normalization/publication uses the local durable ingestion
                  worker. Transport success alone is not dataset success.
                </p>
              )}
              {info.dataset_version_id && (
                <p>
                  Published immutable version:{" "}
                  <ShortId
                    value={info.dataset_version_id}
                    label="published version"
                  />{" "}
                  · <a href="#/v2/catalog">Open catalog and pin this version</a>
                </p>
              )}
              {info.submission_id && (
                <p>
                  <a href={`#/v2/submissions/${info.submission_id}`}>
                    Inspect linked ingestion and attempts
                  </a>
                </p>
              )}
              {!["succeeded", "failed", "cancelled"].includes(info.state) && (
                <button
                  type="button"
                  className="secondary"
                  disabled={cancellation.busy}
                  onClick={() =>
                    void cancellation.run(async () => {
                      controller.current?.abort();
                      await mutate(
                        `import-cancel-${importId}-${info.revision}`,
                        `/v2/imports/${importId}/cancel`,
                        { expected_revision: info.revision },
                      );
                      status.refresh();
                    })
                  }
                >
                  Request durable cancellation
                </button>
              )}
              {["succeeded", "failed", "cancelled"].includes(info.state) && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    freshOperation("import-create");
                    setImportId("");
                    setFile(null);
                    setUpload(null);
                    setConfirmed(false);
                    setStage("");
                    action.clear();
                    cancellation.clear();
                    if (id) navigate("/v2/imports/new");
                  }}
                >
                  Start a fresh import
                </button>
              )}
            </>
          )}
        </section>
      )}
    </>
  );
}

function Research({ capabilities }: { capabilities: Data | null }) {
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
  let workload = "Choose UTC timestamps to estimate workload.";
  try {
    workload = `${((utc(form.end) - utc(form.history_start)) / 300000) * form.instrument_ids.length} five-minute buckets including history across instruments · ${pins.length} pinned versions`;
  } catch {
    /* incomplete input */
  }
  return (
    <>
      <h2>New numerical research</h2>
      <p>
        Choose metadata, pin every daily version including warm-up, and confirm
        the request. Numerical execution needs no model. Generalized copilot and
        memos remain unavailable until Phase 5.
      </p>
      <form
        className="panel v2-form"
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            if (!capabilities)
              throw new Error("Load capabilities before submitting.");
            if (!confirmed)
              throw new Error(
                "Confirm the exact pinned selection and UTC boundaries.",
              );
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
            <option value="market_profile">Market profile</option>
            <option value="cross_asset">Two-instrument comparison</option>
            <option value="volatility_cluster">Volatility clusters</option>
          </select>
        </label>
        <fieldset>
          <legend>
            {form.workflow === "cross_asset"
              ? "Choose exactly two instruments with the same quote asset"
              : "Choose one instrument"}
          </legend>
          {instruments.rows.map((row) => (
            <label className="v2-check" key={row.instrument_id}>
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
              {instrumentLabel(row)}
            </label>
          ))}
        </fieldset>
        {metadata.length > 0 && (
          <Status>{metadata.map(instrumentLabel).join("; ")}</Status>
        )}
        <Field
          title="History start UTC (inclusive)"
          value={form.history_start}
          change={(v) => change("history_start", v)}
          hint="Explicit UTC, aligned to five minutes."
        />
        <Field
          title="Evaluation start UTC (inclusive)"
          value={form.start}
          change={(v) => change("start", v)}
        />
        <Field
          title="Evaluation end UTC (exclusive)"
          value={form.end}
          change={(v) => change("end", v)}
        />
        <fieldset>
          <legend>Metrics</legend>
          {metrics.map((metric) => (
            <label className="v2-check" key={metric}>
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
              {metric.replaceAll("_", " ")}
            </label>
          ))}
        </fieldset>
        {form.workflow === "volatility_cluster" && (
          <p>
            Fixed predicates: volatility quantile 0.9, volume multiple 2,
            minimum 2 bars. At least 300 actual eligible preceding bars
            required.
          </p>
        )}
        <Status>
          {workload} · limits {limits.partitions ?? 62} versions /{" "}
          {limits.research_buckets ?? 17856} buckets
        </Status>
        <label className="v2-check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I confirm these exact versions, UTC boundaries, workflow and metrics.
          The server will verify actual warm-up eligibility.
        </label>
        <button disabled={action.busy || !capabilities}>
          Submit pinned numerical research
        </button>
        <button
          type="button"
          className="secondary"
          disabled={action.busy}
          onClick={() => {
            freshOperation("research-create");
            setConfirmed(false);
            setNote(
              "A fresh operation key is ready. Confirm before submitting; any earlier accepted run remains preserved.",
            );
          }}
        >
          Prepare a fresh research request key
        </button>
      </form>
      <InstrumentPages result={instruments} />
      <ErrorBox>{action.error}</ErrorBox>
      {note && <Status>{note}</Status>}
      <section className="panel">
        <h3>Bounded registered coverage</h3>
        <p>
          Choose up to 62 UTC days to inspect. Alternatives and incomplete pages
          require explicit selection; registered days alone do not establish
          actual bar eligibility.
        </p>
        <div className="v2-form">
          <Field
            title="Coverage from UTC date"
            type="date"
            value={first}
            change={(v) => {
              setFirst(v);
              setCoverage([]);
            }}
          />
          <Field
            title="Coverage before UTC date (exclusive)"
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
                    "Choose 1–2 instruments and a coverage window of at most 62 days.",
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
            Load registered coverage
          </button>
          {!!coverage.length && (
            <button
              type="button"
              disabled={action.busy}
              onClick={() => {
                const suggestion = suggestedWindow(
                  coverage,
                  form.workflow,
                  limits,
                );
                if (!suggestion) {
                  setNote(
                    "No unambiguous contiguous interval fits the selected workflow and limits. Resolve alternatives or choose explicit dates and versions.",
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
                  setNote(
                    "Suggested latest unambiguous interval and exact versions are ready for your confirmation. Actual warm-up remains server-verified.",
                  );
                } catch (e) {
                  setNote(errorText(e));
                }
              }}
            >
              Use latest unambiguous registered interval
            </button>
          )}
        </div>
        {coverage.map((body) => (
          <details key={body.instrument_id}>
            <summary>
              {body.instrument_id} · {body.coverage_claim} · {body.gaps.length}{" "}
              registered daily gaps
            </summary>
            <DataView data={body} />
          </details>
        ))}
      </section>
      <section className="panel">
        <h3>Explicit pinned versions · {pins.length}/62</h3>
        <PinList rows={pins} />
        <p>
          <a href="#/v2/catalog">Choose catalog versions</a>
        </p>
        <label>
          Additional exact registered version IDs (one per line)
          <textarea
            value={pinText}
            onChange={(e) => setPinText(e.target.value)}
          />
        </label>
        <button
          type="button"
          disabled={action.busy}
          onClick={() =>
            void action.run(async () => {
              const ids = [...new Set(pinText.split(/[\s,]+/).filter(Boolean))];
              if (
                !ids.length ||
                ids.length + pins.length > 62 ||
                ids.some((id) => !/^[a-f0-9]{64}$/.test(id))
              )
                throw new Error(
                  "Enter registered 64-hex version IDs within the 62-version bound.",
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
                  trade_date: body.identity?.trade_date ?? legacy?.trade_date,
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
          Verify and add pinned versions
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            saveSelection([]);
            setPins([]);
            setConfirmed(false);
          }}
        >
          Clear all pins
        </button>
      </section>
    </>
  );
}

function NumericalData({
  value,
  name = "Numerical value",
}: {
  value: any;
  name?: string;
}) {
  const [page, setPage] = useState(0);
  if (Array.isArray(value))
    return (
      <section className="v2-result-array">
        <p>
          {name}: {value.length} items · page {page + 1}
        </p>
        {value.slice(page * 50, page * 50 + 50).map((item, i) => (
          <NumericalData
            key={page * 50 + i}
            value={item}
            name={`${name} ${page * 50 + i + 1}`}
          />
        ))}
        <div className="actions">
          {page > 0 && (
            <button
              type="button"
              className="secondary"
              onClick={() => setPage(page - 1)}
            >
              Previous {name} page
            </button>
          )}
          {(page + 1) * 50 < value.length && (
            <button
              type="button"
              className="secondary"
              onClick={() => setPage(page + 1)}
            >
              Next {name} page
            </button>
          )}
        </div>
      </section>
    );
  if (value !== null && typeof value === "object")
    return (
      <dl className="kv">
        {Object.entries(value).map(([key, entry]) => (
          <div key={key}>
            <dt>{key.replaceAll("_", " ")}</dt>
            <dd>
              <NumericalData value={entry} name={key.replaceAll("_", " ")} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return value === null ? (
    <span className="null-value">Unavailable (null)</span>
  ) : (
    <span className="exact">{String(value)}</span>
  );
}
function Run({ id }: { id: string }) {
  const status = useV2(`/v2/research/runs/${id}`, true);
  const summary = useV2(
    status.data?.numerical_available ? `/v2/research/runs/${id}/summary` : null,
  );
  const [wantResults, setWantResults] = useState(false);
  const results = useV2(
    status.data?.numerical_available && wantResults
      ? `/v2/research/runs/${id}/results`
      : null,
  );
  const action = useAction();
  const info = status.data;
  return (
    <>
      <h2>Pinned numerical research</h2>
      <ShortId value={id} label="research run ID" />
      <ErrorBox>{status.error || action.error}</ErrorBox>
      <button type="button" className="secondary" onClick={status.refresh}>
        Refresh research status
      </button>
      {info && (
        <>
          <section className="panel">
            <Tag value={info.state} />
            <p>
              Numerical attempts: {info.attempt_count} · revision{" "}
              {info.revision}
            </p>
            {info.error_code && <ErrorBox>{info.error_code}</ErrorBox>}
            <p>
              Workflow: {info.spec.workflow} · Binance spot · interval{" "}
              {info.spec.interval}
            </p>
            <p>
              History [{info.spec.history_start}, {info.spec.start}) ·
              evaluation [{info.spec.start}, {info.spec.end}) UTC
            </p>
            <p>
              Registered coverage is observed-only; warm-up is excluded from
              reported evaluation totals. Missing buckets remain missing.
            </p>
            {Object.values(info.fingerprint.instruments).map(
              (instrument: any) => (
                <p key={instrument.instrument_id}>
                  {instrument.display_name} · {instrument.instrument_id} · base{" "}
                  {instrument.base_asset} / quote {instrument.quote_asset}
                </p>
              ),
            )}
            <PinList rows={info.fingerprint.datasets as Dataset[]} />
            {!["succeeded", "failed", "cancelled"].includes(info.state) && (
              <>
                <p>
                  Execution uses the local numerical worker; generalized
                  model/memo work is not queued.
                </p>
                <button
                  type="button"
                  disabled={action.busy || info.cancel_requested}
                  onClick={() =>
                    void action.run(async () => {
                      await mutate(
                        `research-cancel-${id}-${info.revision}`,
                        `/v2/research/runs/${id}/cancel`,
                        { expected_revision: info.revision },
                      );
                      status.refresh();
                    })
                  }
                >
                  Request numerical cancellation
                </button>
              </>
            )}
            <Provenance
              data={{
                spec: info.spec,
                fingerprint: info.fingerprint,
                attempts: info.attempts,
              }}
              title="Pinned request, provenance and attempt history"
            />
          </section>
          {info.numerical_available && (
            <>
              <section className="panel">
                <h3>Verified numerical summary</h3>
                <ErrorBox>{summary.error}</ErrorBox>
                {summary.data && <NumericalData value={summary.data} />}
              </section>
              <section className="panel">
                <h3>Verified results</h3>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setWantResults(true)}
                  disabled={results.busy}
                >
                  Load full numerical results
                </button>
                <ErrorBox>{results.error}</ErrorBox>
                {results.data && <NumericalData value={results.data} />}
              </section>
              <Bars info={info} />
            </>
          )}
        </>
      )}
    </>
  );
}
function Bars({ info }: { info: Data }) {
  const spec = info.spec;
  const [instrument, setInstrument] = useState(spec.instrument_ids[0]);
  const [interval, setInterval] = useState("5m");
  // Deliberately blank: research can exceed chart bounds. The user explicitly
  // chooses the chart window; there is no silently truncated initial chart.
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState("");
  const bars = useV2(path);
  const [page, setPage] = useState(0);
  const metadata = info.fingerprint.instruments[instrument];
  const rows = bars.data?.bars as Data[] | undefined;
  const choose = (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const minutes = interval === "1m" ? 1 : 5;
      const first = utc(start, minutes),
        before = utc(end, minutes);
      if (
        first >= before ||
        first < Date.parse(spec.history_start) ||
        before > Date.parse(spec.end)
      )
        throw new Error(
          "Choose a chart window inside the pinned history/evaluation interval.",
        );
      const buckets = (before - first) / (minutes * 60000);
      if (buckets > 1440)
        throw new Error(
          "Chart window exceeds 1,440 buckets; narrow the window or choose five minutes.",
        );
      const days =
        Math.floor((before - 1) / 86400000) - Math.floor(first / 86400000) + 1;
      if (days > 5)
        throw new Error(
          "Chart window touches more than five daily partitions.",
        );
      const versions = info.fingerprint.datasets.filter(
        (row: Data) =>
          row.instrument_id === instrument &&
          row.trade_date >= new Date(first).toISOString().slice(0, 10) &&
          row.trade_date <= new Date(before - 1).toISOString().slice(0, 10),
      );
      const params = new URLSearchParams({
        instrument_id: instrument,
        interval,
        start,
        end,
      });
      versions.forEach((row: Data) =>
        params.append("version", row.dataset_version_id),
      );
      setPath(`/v2/bars?${params.toString()}`);
      setPage(0);
    } catch (e) {
      setError(errorText(e));
    }
  };
  return (
    <section className="panel">
      <h3>Pinned dataset charts</h3>
      <p>
        Explicit chart window: at most 1,440 bars and five touched daily
        partitions. Prices and quote volume use {metadata.quote_asset}; base
        volume uses {metadata.base_asset}.
      </p>
      <form className="v2-form" onSubmit={choose}>
        <label>
          Chart instrument
          <select
            value={instrument}
            onChange={(e) => {
              setInstrument(e.target.value);
              setPath(null);
            }}
          >
            {spec.instrument_ids.map((id: string) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <label>
          Chart interval
          <select
            value={interval}
            onChange={(e) => setInterval(e.target.value)}
          >
            <option value="1m">1 minute</option>
            <option value="5m">5 minutes</option>
          </select>
        </label>
        <Field
          title="Chart start UTC (inclusive)"
          value={start}
          change={setStart}
        />
        <Field title="Chart end UTC (exclusive)" value={end} change={setEnd} />
        <button disabled={bars.busy}>Load pinned chart window</button>
      </form>
      <ErrorBox>{error || bars.error}</ErrorBox>
      {rows && bars.data && (
        <>
          <p>
            Returned {String(bars.data.returned_buckets)} / expected{" "}
            {String(bars.data.expected_buckets)} buckets ·{" "}
            {String(bars.data.empty_buckets)} empty · observed-only
          </p>
          <PriceChart
            rows={rows}
            interval={bars.data.interval}
            start={bars.data.start}
            end={bars.data.end}
            unit={bars.data.units.price}
          />
          <div className="table-scroll">
            <table>
              <caption>
                Exact chart values · page {page + 1}; missing buckets are not
                filled
              </caption>
              <thead>
                <tr>
                  {[
                    "Start UTC",
                    `Open / ${bars.data.units.price}`,
                    `High / ${bars.data.units.price}`,
                    `Low / ${bars.data.units.price}`,
                    `Close / ${bars.data.units.price}`,
                    `VWAP / ${bars.data.units.price}`,
                    `Base volume / ${bars.data.units.base_volume}`,
                    `Quote volume / ${bars.data.units.quote_volume}`,
                    "Trades",
                  ].map((title) => (
                    <th key={title}>{title}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(page * 100, (page + 1) * 100).map((row) => (
                  <tr key={row.start}>
                    {[
                      "start",
                      "open",
                      "high",
                      "low",
                      "close",
                      "vwap",
                      "base_volume",
                      "quote_volume",
                      "trade_count",
                    ].map((key) => (
                      <td key={key}>
                        {row[key] === null
                          ? "Unavailable (null)"
                          : String(row[key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="actions">
            {page > 0 && (
              <button
                type="button"
                className="secondary"
                onClick={() => setPage(page - 1)}
              >
                Previous bars page
              </button>
            )}
            {(page + 1) * 100 < rows.length && (
              <button
                type="button"
                className="secondary"
                onClick={() => setPage(page + 1)}
              >
                Next bars page
              </button>
            )}
          </div>
          <Provenance
            data={{ ...bars.data, bars: undefined }}
            title="Chart pinned provenance and units"
          />
        </>
      )}
    </section>
  );
}
export function chartSegments(
  rows: Data[],
  interval: string,
  start: string,
  end: string,
) {
  const points = rows
    .filter(
      (row) =>
        row.close !== null && row.close !== undefined && row.close !== "",
    )
    .map((row) => ({ x: Date.parse(row.start), y: Number(row.close) }))
    .filter((row) => Number.isFinite(row.x) && Number.isFinite(row.y));
  if (!points.length) return [];
  const min = Math.min(...points.map((p) => p.y)),
    max = Math.max(...points.map((p) => p.y));
  const first = Date.parse(start),
    before = Date.parse(end);
  const step = interval === "1m" ? 60000 : 300000;
  const paths: string[] = [];
  let prior = Number.NaN;
  for (const point of points) {
    const value = `${30 + ((point.x - first) / Math.max(step, before - first)) * 940},${210 - ((point.y - min) / (max - min || 1)) * 180}`;
    if (point.x - prior !== step) paths.push(`M${value}`);
    else paths[paths.length - 1] += ` L${value}`;
    prior = point.x;
  }
  return paths;
}
function PriceChart({
  rows,
  interval,
  start,
  end,
  unit,
}: {
  rows: Data[];
  interval: string;
  start: string;
  end: string;
  unit: string;
}) {
  const segments = chartSegments(rows, interval, start, end);
  return (
    <figure className="v2-chart">
      <figcaption>
        Close price / {unit} · UTC [{start}, {end})
      </figcaption>
      {segments.length ? (
        <svg
          viewBox="0 0 1000 240"
          role="img"
          aria-label={`Close price in ${unit}; gaps are disconnected; exact values in table below`}
        >
          <path d="M30 20V215H980" className="v2-axis" />
          {segments.map((segment, i) => (
            <path key={i} d={segment} className="v2-price" />
          ))}
        </svg>
      ) : (
        <p>No observed bars in this pinned chart window.</p>
      )}
      <p>
        Chart coordinates are display approximations. The table preserves exact
        numerical strings.
      </p>
    </figure>
  );
}
