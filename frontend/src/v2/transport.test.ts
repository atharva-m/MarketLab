import { afterEach, expect, it, vi } from "vitest";
import { hashFile, uploadFile, type Upload } from "./api";

afterEach(() => vi.unstubAllGlobals());
it("sends the exact File with a one-use capability, leaves Content-Length to the browser and supports interruption", async () => {
  class FakeXHR {
    static instance: FakeXHR;
    headers: Record<string, string> = {};
    upload = { onprogress: null as any };
    onload: (() => void) | null = null;
    onerror = null;
    ontimeout = null;
    onabort: (() => void) | null = null;
    status = 200;
    responseText = '{"state":"uploaded"}';
    timeout = 0;
    withCredentials = false;
    body?: Blob;
    method?: string;
    url?: string;
    constructor() {
      FakeXHR.instance = this;
    }
    open(method: string, url: string) {
      this.method = method;
      this.url = url;
    }
    setRequestHeader(name: string, value: string) {
      this.headers[name] = value;
    }
    send(body: Blob) {
      this.body = body;
    }
    abort() {
      this.onabort?.();
    }
  }
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  const file = new File(["canonical bytes"], "source.csv");
  const upload: Upload = {
    method: "PUT",
    url: `/v2/imports/${"a".repeat(8)}-aaaa-aaaa-aaaa-${"a".repeat(12)}/content`,
    generation: "opaque",
    expires_at: "future",
    required_headers: {
      "Content-Type": "application/octet-stream",
      "X-Upload-Token": "private",
    },
  };
  const result = uploadFile(
    upload,
    file,
    vi.fn(),
    new AbortController().signal,
  );
  expect(FakeXHR.instance.body).toBe(file);
  expect(FakeXHR.instance.method).toBe("PUT");
  expect(
    Object.keys(FakeXHR.instance.headers).map((v) => v.toLowerCase()),
  ).not.toContain("content-length");
  FakeXHR.instance.onload?.();
  await expect(result).resolves.toEqual({ state: "uploaded" });
  const own = new AbortController();
  const pending = uploadFile(upload, file, vi.fn(), own.signal);
  own.abort();
  await expect(pending).rejects.toThrow("interrupted");
  await expect(
    uploadFile(
      { ...upload, url: "https://foreign.invalid/content" },
      file,
      vi.fn(),
      own.signal,
    ),
  ).rejects.toThrow();
});

it("terminates the hashing worker on cancellation and never reads the whole File on the UI thread", async () => {
  class FakeWorker {
    static instance: FakeWorker;
    onmessage: any;
    onerror: any;
    terminated = false;
    sent: any;
    constructor() {
      FakeWorker.instance = this;
    }
    terminate() {
      this.terminated = true;
    }
    postMessage(value: any) {
      this.sent = value;
    }
  }
  vi.stubGlobal("Worker", FakeWorker);
  const source = new File(["bytes"], "source.csv");
  const own = new AbortController();
  const pending = hashFile(source, vi.fn(), own.signal);
  expect(FakeWorker.instance.sent.file).toBe(source);
  own.abort();
  await expect(pending).rejects.toThrow("cancelled");
  expect(FakeWorker.instance.terminated).toBe(true);
});
