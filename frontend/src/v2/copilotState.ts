import type { Data } from "../client";
import type { Dataset } from "./api";
import { utc } from "./state";

export const emptyContext = () => ({
  workflow: "",
  instrument_ids: [] as string[],
  start: "",
  end: "",
  history_start: "",
  interval: "",
  metrics: [] as string[],
});
export type ContextForm = ReturnType<typeof emptyContext>;
export const requestId =
  /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export function turnBody(
  text: string,
  form: ContextForm,
  instruments: string[],
) {
  const bytes = new TextEncoder().encode(text).length;
  if (!text.trim() || bytes > 8192)
    throw new Error("Enter a nonempty request of at most 8,192 UTF-8 bytes.");
  if (form.instrument_ids.some((id) => !instruments.includes(id)))
    throw new Error(
      "Context instruments must belong to this frozen selection.",
    );
  const context: Data = {};
  for (const name of [
    "workflow",
    "start",
    "end",
    "history_start",
    "interval",
  ] as const) {
    if (!form[name]) continue;
    if (["start", "end", "history_start"].includes(name)) utc(form[name]);
    context[name] = form[name];
  }
  if (form.instrument_ids.length)
    context.instrument_ids = [...form.instrument_ids].sort();
  if (form.metrics.length) context.metrics = [...form.metrics].sort();
  return { text, context };
}
export function copilotBody(text: string, form: ContextForm, pins: Dataset[]) {
  const ids = [...new Set(pins.map((row) => row.instrument_id))].sort();
  if (!ids.length || ids.length > 2 || !pins.length || pins.length > 62)
    throw new Error(
      "Pin 1–62 daily versions for one or two Binance spot instruments.",
    );
  const days = new Set<string>(),
    versions = new Set<string>();
  for (const pin of pins) {
    const day = `${pin.instrument_id}/${pin.trade_date}`;
    if (days.has(day) || versions.has(pin.dataset_version_id))
      throw new Error(
        "Select one exact version per instrument/day without duplicates.",
      );
    days.add(day);
    versions.add(pin.dataset_version_id);
  }
  return {
    schema: "copilot-request-v2",
    ...turnBody(text, form, ids),
    instrument_ids: ids,
    dataset_versions: [...versions].sort(),
  };
}
export function memoParagraphs(memo: unknown): string[] | null {
  if (typeof memo !== "string") return null;
  const paragraphs = memo.split("\n\n");
  return paragraphs.length === 3 && paragraphs.every((p) => p.trim().length > 0)
    ? paragraphs
    : null;
}
