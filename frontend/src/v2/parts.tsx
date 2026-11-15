/*
 * Shared kit for the /v2 workspace pages. Page modules import everything
 * reusable from here; read the doc comment above each export for its props.
 */
import { useState, type ReactNode } from "react";
import { ErrorBox } from "../components";
import { SERIES, ShortId } from "../ui";
import type { Dataset, Instrument } from "./api";
import { useV2 } from "./hooks";
import { instrumentLabel } from "./state";

/** Builds a query string from the entries that have a non-empty value. */
export const query = (values: Record<string, string | undefined>) =>
  new URLSearchParams(
    Object.entries(values).filter((v): v is [string, string] => !!v[1]),
  ).toString();

/** URL-encodes one path segment. */
export const idPath = (value: string) => encodeURIComponent(value);

/**
 * Labelled text input. `title` is the visible label and the accessible name.
 * `type` defaults to "text", `required` to true. `hint` is one short `<small>`
 * stating a format or limit; `placeholder` shows an example value instead.
 */
export function Field({
  title,
  value,
  change,
  type = "text",
  required = true,
  hint,
  placeholder,
}: {
  title: string;
  value: string;
  change: (value: string) => void;
  type?: string;
  required?: boolean;
  hint?: string;
  placeholder?: string;
}) {
  return (
    <label>
      {title}
      <input
        aria-label={title}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => change(e.target.value)}
        required={required}
      />
      {hint && <small>{hint}</small>}
    </label>
  );
}

/** One muted status line (`role="status"`): short progress or result text. */
export function Status({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="muted">
      {children}
    </p>
  );
}

/** Last `:` segment of an instrument id: `binance:spot:SOLUSDT` gives `SOLUSDT`. */
export const symbolOf = (id: string) => id.slice(id.lastIndexOf(":") + 1);

/** Instrument id to its metadata, for `InstrumentPill` and `PinTable`. */
export const instrumentMap = (rows: Instrument[]) =>
  new Map(rows.map((row) => [row.instrument_id, row]));

/** Stable marker colour index for `id` among `ids` (sorted, de-duplicated). */
export const seriesOf = (ids: string[], id: string) =>
  Math.max(0, [...new Set(ids)].sort().indexOf(id));

/**
 * The `.pair` pill. Props: `id` (instrument id), `instrument` (metadata, from
 * `instrumentMap`), `series` (marker colour index, see `seriesOf`), `small`.
 * With metadata it shows `BASE` and a muted `/QUOTE`; without it only the
 * symbol. Base and quote are never inferred from the symbol text.
 */
export function InstrumentPill({
  id,
  instrument,
  series = 0,
  small,
}: {
  id: string;
  instrument?: Pick<Instrument, "base_asset" | "quote_asset">;
  series?: number;
  small?: boolean;
}) {
  return (
    <span className={small ? "pair small" : "pair"}>
      <i
        className="pair-mark"
        aria-hidden="true"
        style={{ background: SERIES[series % SERIES.length] }}
      />
      <span>
        {instrument ? instrument.base_asset : symbolOf(id)}
        {instrument && <span className="quote">/{instrument.quote_asset}</span>}
      </span>
    </span>
  );
}

/**
 * Pinned dataset versions as a compact table: Instrument, Day, Version.
 * Props: `rows` (datasets), `instruments` (optional `instrumentMap` result).
 * Renders nothing for an empty list; scrolls inside `.table-wrap.pins`.
 */
export function PinTable({
  rows,
  instruments,
}: {
  rows: Dataset[];
  instruments?: Map<string, Instrument>;
}) {
  if (!rows.length) return null;
  const ids = rows.map((row) => row.instrument_id);
  return (
    <div className="table-wrap pins">
      <table>
        <caption>Pinned versions</caption>
        <thead>
          <tr>
            <th>Instrument</th>
            <th>Day</th>
            <th>Version</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.dataset_version_id}>
              <td>
                <InstrumentPill
                  small
                  id={row.instrument_id}
                  instrument={instruments?.get(row.instrument_id)}
                  series={seriesOf(ids, row.instrument_id)}
                />
              </td>
              <td>{row.trade_date}</td>
              <td>
                <ShortId
                  value={row.dataset_version_id}
                  label="pinned version"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Summary strip of label/value pairs. `items` is `[label, value][]`; items
 * whose value is null, undefined or "" are skipped. Values are rendered as is.
 */
export function Facts({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="strip">
      {items
        .filter(
          ([, value]) => value !== null && value !== undefined && value !== "",
        )
        .map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
    </dl>
  );
}

/** Muted "3 of 62" counter. Props: `value`, `max`, optional `testId`. */
export function Count({
  value,
  max,
  testId,
}: {
  value: number | string;
  max: number | string;
  testId?: string;
}) {
  return (
    <span className="count muted" data-testid={testId}>
      {value} of {max}
    </span>
  );
}

/**
 * Section heading row: an `h2` (or `h3` with `level={3}`) and right-aligned
 * `children` such as a `Count` or small actions. `id` goes on the heading.
 */
export function SectionHead({
  title,
  id,
  level = 2,
  children,
}: {
  title: string;
  id?: string;
  level?: 2 | 3;
  children?: ReactNode;
}) {
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <div className="section-head">
      <Heading id={id}>{title}</Heading>
      {children}
    </div>
  );
}

/**
 * Determinate progress in bytes. Props: `label` (stage text), `value` and
 * `max` (bytes). The wrapper is a `role="status"`; the track is a
 * `role="progressbar"`.
 */
export function Meter({
  label,
  value,
  max,
}: {
  label: string;
  value: number;
  max: number;
}) {
  const percent = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div role="status" className="meter">
      <span className="meter-label">{label}</span>
      <div
        className="meter-track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
      >
        <span className="meter-fill" style={{ width: `${percent}%` }} />
      </div>
      <span className="meter-text muted">
        {value.toLocaleString("en-US")} of {max.toLocaleString("en-US")} bytes
      </span>
    </div>
  );
}

/**
 * Previous/next row. Props: `page` (zero-based), `pages` (count), `onPage`
 * (receives the new zero-based page), `label` (noun in the button names, for
 * example "bars"), optional `text` replacing the default "Page 1 of 3" in the
 * middle (for example "1-100 of 250"). Both buttons stay and disable at the ends.
 */
export function Pager({
  page,
  pages,
  onPage,
  label,
  text,
}: {
  page: number;
  pages: number;
  onPage: (page: number) => void;
  label: string;
  text?: ReactNode;
}) {
  return (
    <div className="pagination">
      <button
        type="button"
        className="secondary"
        aria-label={`Previous ${label} page`}
        disabled={page <= 0}
        onClick={() => onPage(page - 1)}
      >
        Previous
      </button>
      <span>{text ?? `Page ${page + 1} of ${Math.max(1, pages)}`}</span>
      <button
        type="button"
        className="secondary"
        aria-label={`Next ${label} page`}
        disabled={page + 1 >= pages}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </div>
  );
}

/** Instrument list state: paged registry reads. `rows` are the current page. */
export function useInstruments() {
  const [cursor, setCursor] = useState("");
  const result = useV2(`/v2/instruments?${query({ limit: "100", cursor })}`);
  return {
    ...result,
    rows: (result.data?.items ?? []) as Instrument[],
    next: () => setCursor(result.data?.next_cursor ?? ""),
    first: () => setCursor(""),
    cursor,
  };
}

/**
 * Instrument select. Props: `rows`, `value`, `onChange`, `enabledOnly`,
 * `title` (label, default "Instrument"), `placeholder` (text of the empty
 * first option), `required` (default true; pass false when the empty option
 * is a valid choice such as "All instruments").
 */
export function InstrumentChoice({
  rows,
  value,
  onChange,
  enabledOnly = false,
  title = "Instrument",
  placeholder = "Choose an instrument",
  required = true,
}: {
  rows: Instrument[];
  value: string;
  onChange: (value: string) => void;
  enabledOnly?: boolean;
  title?: string;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label>
      {title}
      <select
        aria-label={title}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
      >
        <option value="">{placeholder}</option>
        {value && !rows.some((v) => v.instrument_id === value) && (
          <option value={value}>{value}</option>
        )}
        {rows
          .filter((v) => !enabledOnly || v.enabled)
          .map((v) => (
            <option key={v.instrument_id} value={v.instrument_id}>
              {instrumentLabel(v)}
            </option>
          ))}
      </select>
    </label>
  );
}

/**
 * Paging buttons for `useInstruments`: "Next instrument page" and "First
 * instrument page" in an `.actions` row, plus the read error. Renders no row
 * when there is neither a next cursor nor a current cursor.
 */
export function InstrumentPages({
  result,
}: {
  result: ReturnType<typeof useInstruments>;
}) {
  return (
    <>
      <ErrorBox>{result.error}</ErrorBox>
      {(result.data?.next_cursor || result.cursor) && (
        <div className="actions">
          {result.data?.next_cursor && (
            <button type="button" className="secondary" onClick={result.next}>
              Next instrument page
            </button>
          )}
          {result.cursor && (
            <button type="button" className="secondary" onClick={result.first}>
              First instrument page
            </button>
          )}
        </div>
      )}
    </>
  );
}

/**
 * Empty view: a `.notice` with an `h2` `title`, an optional one-line `text`
 * saying what to do next, and `children` (usually link buttons:
 * `<a className="button secondary" href=...>`) in an `.actions` row.
 */
export function EmptyState({
  title,
  text,
  children,
}: {
  title: string;
  text?: string;
  children?: ReactNode;
}) {
  return (
    <section className="notice">
      <h2>{title}</h2>
      {text && <p>{text}</p>}
      {children && <div className="actions">{children}</div>}
    </section>
  );
}
