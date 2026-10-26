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
      {label(String(value ?? "unknown"))}
    </span>
  );
}
export function DataView({ data }: { data: unknown }) {
  if (data === null || data === undefined)
    return <span className="muted">Unavailable (null)</span>;
  if (typeof data !== "object")
    return <span className="exact">{String(data)}</span>;
  if (Array.isArray(data))
    return data.length ? (
      <div className="array">
        {data.map((v, i) => (
          <div key={i}>
            <DataView data={v} />
          </div>
        ))}
      </div>
    ) : (
      <span className="muted">None</span>
    );
  return (
    <dl className="data-grid">
      {Object.entries(data).map(([k, v]) => (
        <div key={k}>
          <dt>{label(k)}</dt>
          <dd>
            <DataView data={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
export function Provenance({
  data,
  title = "Provenance and exact payload",
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
      if (mounted.current) setBusy(false);
    }
  };
  const submit = (body: string) => {
    if (gate.current) return;
    try {
      const op = prepareOperation(slot, path, body);
      void dispatch(op);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const panel = (
    <>
      <ErrorBox>{error}</ErrorBox>
      {saved?.state === "uncertain" && (
        <section className="notice">
          <strong>Saved operation — outcome unresolved</strong>
          <p>
            The API may have accepted this request. Retrying uses the same key
            and exact body. Reloading never submits automatically.
          </p>
          <code>{saved.key}</code>
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
        placeholder="Paste explicit full version IDs or select them in Catalog."
      />
      <small>
        One full ID per line; include history and evaluation days. No latest
        version is selected automatically.
      </small>
    </label>
  );
}
export function PageTitle({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-title">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      {children}
    </header>
  );
}
export function WorkerNotice({ kind }: { kind: string }) {
  return (
    <p className="notice">
      Queued work requires an operator-started bounded {kind} CLI worker. This
      workspace submits and inspects jobs; worker availability and completion
      time are not inferred.
    </p>
  );
}
export function Refresh({ r }: { r: ReturnType<typeof useResource> }) {
  return (
    <div className="actions">
      <button className="secondary" onClick={r.refresh}>
        {r.stopped ? "Resume monitoring" : "Refresh"}
      </button>
      {r.stopped && <span>Automatic monitoring paused after 30 minutes.</span>}
    </div>
  );
}
