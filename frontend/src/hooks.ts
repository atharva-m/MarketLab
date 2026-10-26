import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, request, type Data } from "./client";
export function useResource(
  path: string | null,
  active: (data: Data) => boolean = () => false,
) {
  const [result, setResult] = useState<{
    path: string;
    data: Data;
    cache: string | null;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const [stopped, setStopped] = useState(false);
  const activeRef = useRef(active);
  activeRef.current = active;
  useEffect(() => {
    setError("");
    setResult(null);
    setStopped(false);
    setBusy(false);
    if (!path) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    let started = Date.now();
    let failures = 0;
    let inFlight = false;
    let resume = false;
    const load = async () => {
      if (!live || document.hidden || inFlight) return;
      if (Date.now() - started >= 1_800_000) {
        setStopped(true);
        return;
      }
      const own = new AbortController();
      controller = own;
      inFlight = true;
      setBusy(true);
      try {
        const response = await request(path, { signal: own.signal });
        if (!live || own.signal.aborted) return;
        setResult({ path, data: response.data, cache: response.cache });
        setError("");
        failures = 0;
        if (activeRef.current(response.data))
          timer = setTimeout(() => void load(), 2000);
      } catch (e) {
        if (!live || own.signal.aborted) return;
        setError(e instanceof Error ? e.message : "Request failed");
        failures++;
        if (!(e instanceof ApiError) || e.status === 503)
          timer = setTimeout(
            () => void load(),
            Math.min(10000, 2000 * 2 ** failures),
          );
      } finally {
        inFlight = false;
        if (live) {
          setBusy(false);
          if (resume && !document.hidden) {
            resume = false;
            clearTimeout(timer);
            void load();
          }
        }
      }
    };
    const visible = () => {
      clearTimeout(timer);
      if (document.hidden) {
        resume = false;
        controller?.abort();
      } else {
        started = Date.now();
        setStopped(false);
        if (inFlight) {
          resume = true;
          controller?.abort();
        } else void load();
      }
    };
    document.addEventListener("visibilitychange", visible);
    void load();
    return () => {
      live = false;
      clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", visible);
    };
  }, [path, epoch]);
  return {
    data: result?.path === path ? result.data : null,
    error,
    cache: result?.path === path ? result.cache : null,
    busy,
    stopped,
    refresh: useCallback(() => setEpoch((v) => v + 1), []),
  };
}
export function useRoute() {
  const [route, setRoute] = useState(location.hash.slice(1) || "/catalog");
  useEffect(() => {
    const change = () => setRoute(location.hash.slice(1) || "/catalog");
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  return route;
}
export function navigate(path: string) {
  location.hash = path;
}
