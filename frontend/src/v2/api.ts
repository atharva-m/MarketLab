import { exactParse, type Data } from "../client";
import { Sha256 } from "./sha256";

export type Instrument = Data & {
  instrument_id: string;
  display_name: string;
  source_symbol: string;
  base_asset: string;
  quote_asset: string;
  enabled: boolean;
  revision: number;
};
export type Dataset = Data & {
  dataset_version_id: string;
  instrument_id: string;
  trade_date: string;
  row_count: number | string;
  contract: string;
};
export type Upload = {
  method: "PUT";
  url: string;
  generation: string;
  expires_at: string;
  required_headers: Record<string, string>;
};
export class V2Error extends Error {
  constructor(
    message: string,
    public status: number,
    public code = "unavailable",
    public requestId = "",
  ) {
    super(message);
  }
}
export async function api(
  path: string,
  options: RequestInit = {},
): Promise<Data> {
  if (!/^\/v2\/[A-Za-z0-9_:/?=&%.+-]+$/.test(path) || path.includes("//"))
    throw new Error("Invalid local v2 API path");
  const controller = AbortSignal.timeout(1_860_000);
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    redirect: "error",
    signal: options.signal
      ? AbortSignal.any([options.signal, controller])
      : controller,
  });
  const reader = response.body?.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  if (!reader)
    throw new V2Error("The API returned no response.", response.status);
  try {
    for (;;) {
      const next = await reader.read();
      if (next.done) break;
      size += next.value.length;
      if (size > 16 * 1024 ** 2)
        throw new Error("The API response exceeds its bound.");
      chunks.push(next.value);
    }
  } finally {
    await reader.cancel();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const part of chunks) {
    bytes.set(part, offset);
    offset += part.length;
  }
  let data: Data;
  try {
    data = exactParse(new TextDecoder().decode(bytes));
  } catch {
    throw new V2Error(
      "The API returned an unreadable response.",
      response.status,
    );
  }
  if (!response.ok) {
    const error = data?.error;
    throw new V2Error(
      typeof error?.message === "string"
        ? error.message
        : "The operation failed.",
      response.status,
      typeof error?.code === "string" ? error.code : "unavailable",
      typeof error?.request_id === "string" ? error.request_id : "",
    );
  }
  return data;
}

const operations = new Map<
  string,
  { key: string; fingerprint: string; result?: Data }
>();
export function freshOperation(slot: string) {
  operations.delete(slot);
  try {
    localStorage.removeItem(`marketlab.v2.op.${slot}`);
  } catch {
    /* session key cleared */
  }
}
export async function mutate(
  slot: string,
  path: string,
  body: Data,
  method = "POST",
) {
  const text = JSON.stringify(body);
  if (new TextEncoder().encode(text).length > 65536)
    throw new Error("Control request exceeds 64 KiB.");
  const fingerprint = new Sha256()
    .update(new TextEncoder().encode(`${method}:${path}:${text}`))
    .digest();
  let operation = operations.get(slot);
  if (!operation || operation.fingerprint !== fingerprint) {
    // Only opaque operation keys/fingerprints are persisted. Never responses,
    // manifests, raw file data or upload capabilities.
    let saved: { key: string; fingerprint: string } | null = null;
    try {
      saved = JSON.parse(
        localStorage.getItem(`marketlab.v2.op.${slot}`) ?? "null",
      );
    } catch {
      /* unavailable storage */
    }
    operation =
      saved?.fingerprint === fingerprint &&
      /^[A-Za-z0-9_.-]{1,128}$/.test(saved.key)
        ? saved
        : { key: `v2ui.${crypto.randomUUID()}`, fingerprint };
    operations.set(slot, operation);
    try {
      localStorage.setItem(
        `marketlab.v2.op.${slot}`,
        JSON.stringify({ key: operation.key, fingerprint }),
      );
    } catch {
      /* session replay still available */
    }
  }
  // An in-memory response is an operation recovery too. In particular, never
  // mistake the immutable original create response for a fresh upload grant.
  if (operation.result) return { ...operation.result, replayed: true };
  const result = await api(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": operation.key,
    },
    body: text,
  });
  operation.result = result;
  return result;
}

export function hashFile(
  file: File,
  progress: (bytes: number) => void,
  signal: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Hashing cancelled", "AbortError"));
      return;
    }
    const worker = new Worker(new URL("./hash.worker.ts", import.meta.url), {
      type: "module",
    });
    const close = () => {
      worker.terminate();
      signal.removeEventListener("abort", abort);
    };
    const abort = () => {
      close();
      reject(new DOMException("Hashing cancelled", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
    worker.onmessage = ({ data }) => {
      if (data.kind === "progress") progress(data.bytes);
      else if (data.kind === "done" && /^[a-f0-9]{64}$/.test(data.sha256)) {
        close();
        resolve(data.sha256);
      } else {
        close();
        reject(
          new Error("The file could not be hashed. Reselect it and retry."),
        );
      }
    };
    worker.onerror = () => {
      close();
      reject(new Error("File hashing failed."));
    };
    worker.postMessage({ file });
  });
}

export function uploadFile(
  upload: Upload,
  file: File,
  progress: (bytes: number) => void,
  signal: AbortSignal,
): Promise<Data> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Upload cancelled", "AbortError"));
      return;
    }
    if (
      !/^\/v2\/imports\/[a-f0-9-]{36}\/content$/.test(upload.url) ||
      upload.method !== "PUT"
    ) {
      reject(new Error("The API returned an invalid upload destination."));
      return;
    }
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const close = () => signal.removeEventListener("abort", abort);
    xhr.open("PUT", upload.url);
    xhr.timeout = 1_860_000;
    xhr.withCredentials = true;
    for (const [name, value] of Object.entries(upload.required_headers)) {
      if (!["content-type", "x-upload-token"].includes(name.toLowerCase())) {
        reject(new Error("The API returned an unsupported upload header."));
        return;
      }
      xhr.setRequestHeader(name, value);
    }
    xhr.upload.onprogress = (event) => progress(event.loaded);
    xhr.onload = () => {
      close();
      let body: Data;
      try {
        body = exactParse(xhr.responseText);
      } catch {
        reject(new Error("Upload outcome is unconfirmed. Refresh status."));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else
        reject(
          new V2Error(
            body?.error?.message ??
              "Upload failed. Refresh status before renewal.",
            xhr.status,
            body?.error?.code,
            body?.error?.request_id,
          ),
        );
    };
    xhr.onerror = xhr.ontimeout = () => {
      close();
      reject(
        new Error(
          "Upload outcome is unconfirmed. Refresh status before renewal.",
        ),
      );
    };
    xhr.onabort = () => {
      close();
      reject(
        new DOMException(
          "Upload interrupted. Refresh durable status.",
          "AbortError",
        ),
      );
    };
    signal.addEventListener("abort", abort, { once: true });
    // File/Blob provides exact known length. Browser owns Content-Length.
    xhr.send(file);
  });
}
