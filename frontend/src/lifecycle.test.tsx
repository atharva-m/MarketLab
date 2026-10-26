import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useResource } from "./hooks";
import { ApiError, request } from "./client";
import { DataView, useMutation } from "./components";
vi.mock("./client", async (original) => ({
  ...(await original<typeof import("./client")>()),
  request: vi.fn(),
}));
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: false,
  });
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
  vi.clearAllMocks();
});
function Probe({ path }: { path: string | null }) {
  const r = useResource(path, () => true);
  return (
    <div>
      {r.data?.name ?? "empty"}|{r.error}|{r.busy ? "busy" : "idle"}
    </div>
  );
}
it("drops obsolete response immediately when chart/request becomes null", async () => {
  vi.mocked(request).mockResolvedValue({
    data: { name: "old chart" },
    cache: null,
  });
  await act(async () => root.render(<Probe path="/v1/old" />));
  expect(container.textContent).toContain("old chart");
  await act(async () => root.render(<Probe path={null} />));
  expect(container.textContent).toContain("empty");
});
it.each([404, 409, 422])(
  "stops automatic retries for permanent HTTP%s",
  async (status) => {
    vi.mocked(request).mockRejectedValue(
      new ApiError("Permanent failure", status),
    );
    await act(async () => root.render(<Probe path="/v1/item" />));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(request).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("Permanent failure");
  },
);
it("backs off transient503 and stops when navigation replaces resource", async () => {
  vi.mocked(request).mockRejectedValue(new ApiError("Unavailable", 503));
  await act(async () => root.render(<Probe path="/v1/item" />));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(4000);
  });
  expect(request).toHaveBeenCalledTimes(2);
  await act(async () => root.render(<Probe path={null} />));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30000);
  });
  expect(request).toHaveBeenCalledTimes(2);
});
it("does not overlap rapid hidden/visible loads or install aborted response", async () => {
  let finish!: (v: { data: { name: string }; cache: null }) => void;
  vi.mocked(request)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValue({ data: { name: "new" }, cache: null });
  await act(async () => root.render(<Probe path="/v1/item" />));
  await act(async () => {
    Object.defineProperty(document, "hidden", { value: true });
    document.dispatchEvent(new Event("visibilitychange"));
    Object.defineProperty(document, "hidden", { value: false });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  expect(request).toHaveBeenCalledTimes(1);
  await act(async () => finish({ data: { name: "obsolete" }, cache: null }));
  expect(request).toHaveBeenCalledTimes(2);
  expect(container.textContent).toContain("new");
  expect(container.textContent).not.toContain("obsolete");
});
it("renders untrusted HTML and null statistics as text", () => {
  const html = renderToStaticMarkup(
    <DataView
      data={{
        claim: "<img src=x onerror=alert(1)>",
        value: null,
        reason: "zero_variance",
        observation_count: 2,
      }}
    />,
  );
  expect(html).toContain("&lt;img");
  expect(html).not.toContain("<img");
  expect(html).toContain("Unavailable (null)");
  expect(html).toContain("zero_variance");
});
it("synchronously gates duplicate mutation dispatch and suppresses unmounted navigation", async () => {
  const done = vi.fn();
  let resolve!: (response: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((r) => {
          resolve = r;
        }),
    ),
  );
  function Form() {
    const m = useMutation("test", "/v1/research/runs", done);
    return (
      <button
        onClick={() => {
          m.submit("{}");
          m.submit("{}");
        }}
      >
        Submit
      </button>
    );
  }
  await act(async () => root.render(<Form />));
  await act(async () => container.querySelector("button")!.click());
  expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () => root.render(<div>Elsewhere</div>));
  await act(async () =>
    resolve(new Response('{"run_id":"accepted"}', { status: 201 })),
  );
  expect(done).not.toHaveBeenCalled();
  expect(
    JSON.parse(localStorage.getItem("marketlab.operations.v1")!)[0].state,
  ).toBe("resolved");
  vi.unstubAllGlobals();
});
