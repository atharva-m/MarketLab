import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ApiError,
  discardOperation,
  prepareOperation,
  sendOperation,
  storedOperation,
  type Data,
  type Operation,
} from "./client";
import { useResource } from "./hooks";
import { Exact, ShortId } from "./ui";
export const active = (d: Data) =>
  ["queued", "running", "retry_wait", "pending"].includes(d.state ?? d.status);
export const label = (s: string) => s.replaceAll("_", " ");
export function ErrorBox({ children }: { children: ReactNode }) {
  return children ? (
    <div className="error" role="alert">
      {children}
    </div>
  ) : null;
}
export function Tag({ value }: { value: unknown }) {
  return (
    <span className={`tag ${String(value)}`}>
      <span className="tag-text">{label(String(value ?? "unknown"))}</span>
    </span>
  );
}
export function DataView({
  data,
  name = "value",
}: {
  data: unknown;
  name?: string;
}) {
  if (data === null || data === undefined)
    return <span className="null-value">Unavailable (null)</span>;
  if (typeof data === "string" && /^[a-f0-9]{64}$/.test(data))
    return <ShortId value={data} label={label(name)} />;
  if (typeof data === "string" && /^-?\d+\.\d+$/.test(data))
    return <Exact value={data} />;
  if (typeof data !== "object")
    return <span className="exact">{String(data)}</span>;
  if (Array.isArray(data))
    return data.length ? (
      <div className="array">
        {data.map((v, i) => (
          <div key={i}>
            <DataView data={v} name={name} />
          </div>
        ))}
      </div>
    ) : (
      <span className="muted">None</span>
    );
  return (
    <dl className="kv">
      {Object.entries(data).map(([k, v]) => (
        <div key={k}>
          <dt>{label(k)}</dt>
          <dd>
            <DataView data={v} name={k} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
export function Provenance({
  data,
  title = "Raw JSON",
}: {
  data: unknown;
  title?: string;
}) {
  return (
    <details className="provenance">
      <summary>{title}</summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}
export function useMutation(
  slot: string,
  path: string,
  onDone: (data: Data) => void,
) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Operation | undefined>(() =>
    storedOperation(slot),
  );
  // A first attempt still in flight shows as validating, not as unconfirmed.
  const [first, setFirst] = useState("");
  const gate = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    setSaved(storedOperation(slot));
    setError("");
  }, [slot]);
  const dispatch = async (op: Operation) => {
    if (gate.current) return;
    gate.current = true;
    setBusy(true);
    setError("");
    setSaved(op);
    try {
      const result = await sendOperation(op);
      if (!mounted.current) return;
      setSaved(storedOperation(slot));
      onDone(result);
    } catch (e) {
      if (!mounted.current) return;
      setError(e instanceof Error ? e.message : "Submission failed");
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        path.includes("/clarifications")
      )
        window.dispatchEvent(new Event("marketlab-conflict"));
    } finally {
      gate.current = false;
      if (mounted.current) {
        setBusy(false);
        setFirst("");
      }
    }
  };
  const submit = (body: string) => {
    if (gate.current) return;
    try {
      const op = prepareOperation(slot, path, body);
      setFirst(op.id);
      void dispatch(op);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const panel = (
    <>
      <ErrorBox>{error}</ErrorBox>
      {saved?.state === "uncertain" && saved.id !== first && (
        <section className="notice">
          <strong>The last request has no confirmed outcome</strong>
          <p>
            The server may already have accepted it. Retrying sends the same key
            and body, so it cannot be applied twice. Reloading never resends it.
          </p>
          <Provenance
            data={saved.body ? JSON.parse(saved.body) : {}}
            title="Review saved request"
          />
          <div className="actions">
            <button
              type="button"
              disabled={busy}
              onClick={() => void dispatch(saved)}
            >
              Retry saved operation
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    "The original operation may already be accepted. Discard its saved replay key and allow a new operation?",
                  )
                ) {
                  discardOperation(saved.id);
                  setSaved(undefined);
                  setError("");
                }
              }}
            >
              Discard saved operation
            </button>
          </div>
        </section>
      )}
    </>
  );
  return { busy, submit, panel };
}
export function VersionInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (s: string) => void;
}) {
  return (
    <label className="wide">
      Dataset version IDs
      <textarea
        data-testid="dataset-version-ids"
        rows={4}
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Paste full version IDs, or select days in Datasets."
      />
      <small>
        One ID per line. Include warm-up and evaluation days; nothing is
        selected automatically.
      </small>
    </label>
  );
}
export function PageTitle({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="page-title">
      <div>
        <h1>{title}</h1>
        {meta}
      </div>
      {children}
    </header>
  );
}
export function Refresh({ r }: { r: ReturnType<typeof useResource> }) {
  return (
    <div className="actions">
      <button className="secondary" onClick={r.refresh}>
        {r.stopped ? "Resume updates" : "Refresh"}
      </button>
      {r.stopped && (
        <span className="muted">Updates paused after 30 minutes.</span>
      )}
    </div>
  );
}
