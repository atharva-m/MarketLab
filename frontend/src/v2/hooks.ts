import { useCallback, useEffect, useRef, useState } from "react";
import type { Data } from "../client";
import { api, V2Error } from "./api";

export const active = (data: Data) =>
  ["queued", "running", "retry_wait", "uploading"].includes(data.state) ||
  (Array.isArray(data.jobs) &&
    data.jobs.some((job: Data) =>
      ["queued", "running", "retry_wait"].includes(job.state),
    ));
export function useV2(path: string | null, poll = false) {
  const [result, setResult] = useState<{ path: string; data: Data } | null>(
    null,
  );
  const [error, setError] = useState("");
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [epoch, setEpoch] = useState(0);
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const started = Date.now();
    setError("");
    setErrorStatus(null);
    setBusy(false);
    if (!path) return () => controller.abort();
    const load = async () => {
      if (
        !live ||
        controller.signal.aborted ||
        Date.now() - started > 1_800_000
      )
        return;
      setBusy(true);
      try {
        const data = await api(path, { signal: controller.signal });
        if (!live) return;
        setResult({ path, data });
        setError("");
        setErrorStatus(null);
        if (poll && active(data)) timer = setTimeout(() => void load(), 2000);
      } catch (e) {
        if (!live || controller.signal.aborted) return;
        setError(errorText(e));
        setErrorStatus(e instanceof V2Error ? e.status : null);
      } finally {
        if (live) setBusy(false);
      }
    };
    void load();
    return () => {
      live = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [path, poll, epoch]);
  return {
    data: result?.path === path ? result.data : null,
    error,
    errorStatus,
    busy,
    refresh: useCallback(() => setEpoch((v) => v + 1), []),
  };
}
export function errorText(error: unknown) {
  return error instanceof V2Error
    ? `${error.message} (${error.code}${error.requestId ? `; request ${error.requestId}` : ""})`
    : error instanceof Error
      ? error.message
      : "The operation failed.";
}
export function useAction() {
  const gate = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (operation: () => Promise<unknown>) => {
    if (gate.current) return;
    gate.current = true;
    setBusy(true);
    setError("");
    try {
      await operation();
    } catch (e) {
      setError(errorText(e));
    } finally {
      gate.current = false;
      setBusy(false);
    }
  };
  return { busy, error, run, clear: () => setError("") };
}
