import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { Memo } from "./Copilot";

const fixture = vi.hoisted(() => ({
  data: null as Record<string, any> | null,
  error: "",
  errorStatus: null as number | null,
}));
vi.mock("./hooks", async (original) => ({
  ...(await original<typeof import("./hooks")>()),
  useV2: () => ({ ...fixture, busy: false, refresh: vi.fn() }),
}));
const id = "44444444-4444-4444-8444-444444444444";
it("keeps a failed memo supplemental and terminal without reset controls", () => {
  fixture.data = {
    state: "failed",
    model_calls: 2,
    error_code: "model_unavailable",
  };
  fixture.error = "";
  fixture.errorStatus = null;
  const html = renderToStaticMarkup(<Memo id={id} available />);
  expect(html).toContain("model_unavailable");
  expect(html).toContain("The numerical result is retained");
  expect(html).not.toContain("Queue supplemental memo");
});
it("reads completed plain-text memo even when enqueue capability is unavailable", () => {
  fixture.data = {
    state: "succeeded",
    model_calls: 1,
    memo: "<script>bad()</script>\n\n**plain**\n\nThird paragraph.",
  };
  const html = renderToStaticMarkup(<Memo id={id} available={false} />);
  const container = document.createElement("div");
  container.innerHTML = html;
  expect(container.querySelectorAll(".v2-memo-text p")).toHaveLength(3);
  expect(container.querySelectorAll("script,strong")).toHaveLength(0);
  expect(container.textContent).toContain("<script>bad()</script>");
  expect(container.textContent).toContain("**plain**");
});
it("distinguishes a missing memo from an unavailable read", () => {
  fixture.data = null;
  fixture.error = "Missing memo";
  fixture.errorStatus = 404;
  let html = renderToStaticMarkup(<Memo id={id} available />);
  expect(html).toContain("Queue supplemental memo");
  expect(html).not.toContain('role="alert"');
  fixture.error = "Storage unavailable";
  fixture.errorStatus = 503;
  html = renderToStaticMarkup(<Memo id={id} available />);
  expect(html).toContain("Storage unavailable");
  expect(html).not.toContain("Queue supplemental memo");
});
