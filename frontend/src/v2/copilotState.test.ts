import { expect, it } from "vitest";
import {
  copilotBody,
  emptyContext,
  memoParagraphs,
  turnBody,
} from "./copilotState";
import type { Dataset } from "./api";
const pin = (
  instrument: string,
  version: string,
  day = "2025-03-01",
): Dataset => ({
  instrument_id: instrument,
  dataset_version_id: version.repeat(64),
  trade_date: day,
  row_count: 10,
  contract: "dataset-manifest-v2",
});
it("builds an exact selected request without inserting numerical defaults", () => {
  const pins = [
    pin("binance:spot:SOLUSDT", "d"),
    pin("binance:spot:BTCUSDT", "a"),
  ];
  expect(copilotBody("Compare these", emptyContext(), pins)).toEqual({
    schema: "copilot-request-v2",
    text: "Compare these",
    context: {},
    instrument_ids: ["binance:spot:BTCUSDT", "binance:spot:SOLUSDT"],
    dataset_versions: ["a".repeat(64), "d".repeat(64)],
  });
});
it("enforces selected context, alternative-day and two-instrument boundaries", () => {
  expect(() => copilotBody("x", emptyContext(), [])).toThrow("Pin 1–62");
  expect(() =>
    copilotBody("x", emptyContext(), [
      pin("a", "a"),
      pin("b", "b"),
      pin("c", "c"),
    ]),
  ).toThrow("one or two");
  expect(() =>
    copilotBody("x", emptyContext(), [pin("a", "a"), pin("a", "b")]),
  ).toThrow("one exact version");
  expect(() =>
    turnBody("x", { ...emptyContext(), instrument_ids: ["foreign"] }, [
      "selected",
    ]),
  ).toThrow("frozen selection");
});
it("uses UTF-8 byte bounds and only explicit aligned UTC context", () => {
  expect(() => turnBody("é".repeat(4097), emptyContext(), [])).toThrow("8,192");
  expect(() => turnBody("   ", emptyContext(), [])).toThrow("nonempty");
  const form = {
    ...emptyContext(),
    start: "2025-03-01T01:00:00Z",
    metrics: ["profile"],
    interval: "5m",
  };
  expect(turnBody("profile", form, []).context).toEqual({
    start: form.start,
    metrics: ["profile"],
    interval: "5m",
  });
  expect(() =>
    turnBody("x", { ...form, start: "2025-03-01T01:01:00Z" }, []),
  ).toThrow("align");
});
it("accepts exactly three plain-text memo paragraphs without interpreting markup", () => {
  expect(
    memoParagraphs("<script>unsafe()</script>\n\n**literal**\n\nThree."),
  ).toEqual(["<script>unsafe()</script>", "**literal**", "Three."]);
  for (const value of [
    null,
    "one",
    "one\n\ntwo",
    "one\n\n\n\nthree",
    "one\n\ntwo\n\nthree\n\nfour",
  ])
    expect(memoParagraphs(value)).toBeNull();
});
