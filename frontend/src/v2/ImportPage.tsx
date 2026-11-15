import { useEffect, useRef, useState, type FormEvent } from "react";
import { ErrorBox, PageTitle, Tag } from "../components";
import { navigate } from "../hooks";
import { CopyButton, ShortId, WorkerHint, stamp } from "../ui";
import {
  api,
  freshOperation,
  hashFile,
  mutate,
  uploadFile,
  type Upload,
} from "./api";
import { useAction, useV2 } from "./hooks";
import {
  Field,
  InstrumentChoice,
  InstrumentPages,
  Facts,
  Meter,
  Status,
  useInstruments,
} from "./parts";

const CSV_HEADER =
  "source_trade_id,executed_at,price,quantity,quote_quantity,is_buyer_maker,is_best_match";
const ENCODINGS: Record<string, string> = {
  rfc3339_utc: "RFC 3339, UTC",
  unix_seconds: "Unix seconds",
  unix_milliseconds: "Unix milliseconds",
  unix_microseconds: "Unix microseconds",
  arrow_timestamp_us_utc: "Arrow timestamp[us, UTC]",
};
const RECOVERED = "This import already exists. Showing its current status.";

export function Import({ id }: { id?: string }) {
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
    setStage("Uploading");
    setBytes(0);
    // Retire the in-memory capability at dispatch; any uncertain outcome is
    // resolved through durable status, never automatic byte retry.
    setUpload(null);
    await uploadFile(capability, source, setBytes, signal);
    setStage("Uploaded");
    status.refresh();
  };
  const selectedFile = () => {
    if (!file || file.size <= 0 || file.size > 4 * 1024 ** 3)
      throw new Error("Choose a file of at most 4 GiB.");
    return file;
  };
  const create = (event: FormEvent) => {
    event.preventDefault();
    void action.run(async () => {
      const source = selectedFile();
      if (!confirmed) throw new Error("Confirm the file before uploading.");
      const own = new AbortController();
      controller.current = own;
      setStage("Hashing");
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
          setStage(RECOVERED);
          status.refresh();
          return;
        }
        setUpload(capability);
        if (result.state === "awaiting_upload")
          await send(capability, source, own.signal);
        else {
          setStage(RECOVERED);
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
      if (!info) throw new Error("Refresh the status first.");
      if (source.size !== Number(info.declared_bytes))
        throw new Error("Choose the original file (same size).");
      const own = new AbortController();
      controller.current = own;
      try {
        setStage("Checking file");
        setBytes(0);
        const hash = await hashFile(source, setBytes, own.signal);
        if (hash !== info.source_sha256)
          throw new Error("This file does not match the original.");
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
          throw new Error("The upload link is missing. Refresh and retry.");
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
  const terminal = ["succeeded", "failed", "cancelled"];
  return (
    <>
      <PageTitle title="Import">
        {!importId && lastImport && (
          <div className="title-actions">
            <a className="button secondary" href={`#/v2/imports/${lastImport}`}>
              Last import
            </a>
          </div>
        )}
      </PageTitle>
      <div className="narrow">
        <details className="provenance">
          <summary>File format</summary>
          <div className="code-row">
            <code>{CSV_HEADER}</code>
            <CopyButton value={CSV_HEADER} label="CSV header" />
          </div>
          <dl className="kv">
            <div>
              <dt>source_trade_id</dt>
              <dd>string</dd>
            </div>
            <div>
              <dt>executed_at</dt>
              <dd>timestamp[us, UTC]</dd>
            </div>
            <div>
              <dt>price, quantity, quote_quantity</dt>
              <dd>decimal128(38,18)</dd>
            </div>
            <div>
              <dt>is_buyer_maker, is_best_match</dt>
              <dd>boolean, nullable</dd>
            </div>
          </dl>
        </details>
        {!importId && (
          <form className="panel" onSubmit={create}>
            <div className="fields">
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
                title="Trade date"
                type="date"
                value={form.trade_date}
                change={(v) => {
                  setForm({ ...form, trade_date: v });
                  setConfirmed(false);
                }}
              />
              <label>
                Format
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
                Timestamps
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
                    <option key={encoding} value={encoding}>
                      {ENCODINGS[encoding]}
                    </option>
                  ))}
                </select>
              </label>
              <Field
                title="Source name"
                value={form.source_name}
                change={(v) => setForm({ ...form, source_name: v })}
                placeholder="binance-export-2025-03"
              />
              <label>
                <span>
                  Source reference <span className="note">Optional</span>
                </span>
                <input
                  aria-label="Source reference"
                  type="text"
                  value={form.source_reference}
                  onChange={(e) =>
                    setForm({ ...form, source_reference: e.target.value })
                  }
                />
              </label>
            </div>
            <label>
              File
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
            <label className="check">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              This is Binance spot trade data in the required format
            </label>
            <div className="actions">
              <button disabled={action.busy}>Upload</button>
            </div>
          </form>
        )}
        {!importId && <InstrumentPages result={instruments} />}
        <ErrorBox>
          {action.error || cancellation.error || status.error}
        </ErrorBox>
        {stage === RECOVERED && <Status>{stage}</Status>}
        {stage && stage !== RECOVERED && (
          <>
            {file ? (
              <Meter label={stage} value={bytes} max={file.size} />
            ) : (
              <Status>{stage}</Status>
            )}
          </>
        )}
        {action.busy && (
          <div className="actions">
            <button
              type="button"
              className="secondary"
              onClick={() => controller.current?.abort()}
            >
              Stop
            </button>
          </div>
        )}
        {importId && (
          <section className="panel">
            <div className="toolbar">
              <h2>Status</h2>
              <div className="actions">
                {info && <Tag value={info.state} />}
                {!id && <a href={`#/v2/imports/${importId}`}>Permalink</a>}
                <button
                  type="button"
                  className="secondary"
                  onClick={status.refresh}
                >
                  Refresh
                </button>
              </div>
            </div>
            {info && (
              <>
                <Facts
                  items={[
                    ["Import", <ShortId value={importId} label="import ID" />],
                    [
                      "Received",
                      `${String(info.received_bytes)} of ${String(info.declared_bytes)} bytes`,
                    ],
                    [
                      "Source SHA-256",
                      <ShortId
                        value={info.source_sha256}
                        label="source SHA-256"
                      />,
                    ],
                    ["Revision", info.revision],
                    [
                      "Link expires",
                      expiry &&
                      ["awaiting_upload", "upload_failed"].includes(info.state)
                        ? stamp(expiry)
                        : null,
                    ],
                    [
                      "Version",
                      info.dataset_version_id ? (
                        <ShortId
                          value={info.dataset_version_id}
                          label="published version"
                        />
                      ) : null,
                    ],
                  ]}
                />
                {info.error && (
                  <ErrorBox>{info.error.message ?? info.error.code}</ErrorBox>
                )}
                {["awaiting_upload", "upload_failed"].includes(info.state) && (
                  <>
                    <label>
                      Original file
                      <input
                        type="file"
                        accept=".csv,.parquet"
                        disabled={action.busy}
                        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                      />
                    </label>
                    <div className="actions">
                      <button
                        type="button"
                        disabled={action.busy || (!upload && !mayRenew)}
                        onClick={recoverUpload}
                      >
                        {upload ? "Resume upload" : "Renew and upload"}
                      </button>
                    </div>
                  </>
                )}
                {info.state === "uploaded" && (
                  <div className="actions">
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
                      Finalize import
                    </button>
                  </div>
                )}
                {["queued", "running", "retry_wait"].includes(info.state) &&
                  info.submission_id && (
                    <WorkerHint
                      kind="ingestion_v2"
                      id={info.submission_id}
                      jobs={1}
                      running={info.state === "running"}
                    />
                  )}
                <div className="actions">
                  {info.dataset_version_id && (
                    <a className="button secondary" href="#/v2/catalog">
                      Open catalog
                    </a>
                  )}
                  {info.submission_id && (
                    <a
                      className="button secondary"
                      href={`#/v2/submissions/${info.submission_id}`}
                    >
                      View ingestion
                    </a>
                  )}
                  {!terminal.includes(info.state) && (
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
                      Cancel import
                    </button>
                  )}
                  {terminal.includes(info.state) && (
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
                      New import
                    </button>
                  )}
                </div>
              </>
            )}
          </section>
        )}
      </div>
    </>
  );
}
