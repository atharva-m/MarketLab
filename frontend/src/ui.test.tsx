import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { Exact, ShortId, CopyButton } from "./ui";

it("exact presentation keeps every decimal digit and integer lexeme", () => {
  const container = document.createElement("div");
  for (const value of [
    "12345.123456789012345678",
    "0.000000000000000001",
    "9223372036854775807",
    "-10.000000000000000000",
  ]) {
    container.innerHTML = renderToStaticMarkup(<Exact value={value} />);
    expect(container.textContent).toBe(value);
  }
});

it("short IDs retain the full accessible value and copy the original", async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  const value = "a".repeat(64);
  const writeText = vi.fn().mockResolvedValue(undefined);
  const original = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(<ShortId value={value} label="version ID" />),
    );
    expect(container.querySelector(".sr-only")!.textContent).toBe(value);
    expect(container.querySelector("code")!.title).toBe(value);
    await act(async () => container.querySelector("button")!.click());
    expect(writeText).toHaveBeenCalledExactlyOnceWith(value);
    await act(async () =>
      root.render(<CopyButton value={value} label="hash" />),
    );
    writeText.mockRejectedValueOnce(new Error("Clipboard unavailable"));
    await act(async () => container.querySelector("button")!.click());
    expect(container.querySelector("button")!.getAttribute("aria-label")).toBe(
      "Copy hash",
    );
  } finally {
    await act(async () => root.unmount());
    if (original) Object.defineProperty(navigator, "clipboard", original);
    else Reflect.deleteProperty(navigator, "clipboard");
  }
});
