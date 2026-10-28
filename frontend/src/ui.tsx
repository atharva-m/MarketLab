import { useEffect, useState, type ReactNode } from "react";
import type { Data } from "./client";
const ICONS = {
  datasets: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </>
  ),
  ingestion: (
    <>
      <path d="M12 3.5v11" />
      <path d="m7.5 10 4.5 4.5 4.5-4.5" />
      <path d="M4 16.5v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </>
  ),
  jobs: (
    <>
      <path d="M10 6h10M10 12h10M10 18h10" />
      <path d="m3.5 6 1.5 1.5L7.5 5M3.5 12l1.5 1.5L7.5 11M3.5 18l1.5 1.5L7.5 17" />
    </>
  ),
  research: (
    <>
      <path d="M3.5 3.5v17h17" />
      <path d="m7.5 15 3.5-4.5 3 3 5-6.5" />
    </>
  ),
  copilot: (
    <path d="M12 3.5 13.9 10 20.5 12l-6.6 2L12 20.5 10.1 14 3.5 12l6.6-2z" />
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" />
    </>
  ),
  copy: (
    <>
      <rect x="9" y="9" width="11.5" height="11.5" rx="2" />
      <path d="M15 5.5V5a1.5 1.5 0 0 0-1.5-1.5h-8A1.5 1.5 0 0 0 4 5v8a1.5 1.5 0 0 0 1.5 1.5H6" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  terminal: (
    <>
      <rect x="3" y="4.5" width="18" height="15" rx="2" />
      <path d="m7 9.5 2.5 2.5L7 14.5M12.5 14.5h4.5" />
    </>
  ),
  hash: <path d="M5 9h14M5 15h14M10.5 3.5l-2 17M15.5 3.5l-2 17" />,
  run: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m10 8.5 5 3.5-5 3.5z" />
    </>
  ),
  left: <path d="m14.5 6-6 6 6 6" />,
  right: <path d="m9.5 6 6 6-6 6" />,
  close: <path d="M17.5 6.5l-11 11M6.5 6.5l11 11" />,
};
export type IconName = keyof typeof ICONS;
export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {ICONS[name]}
    </svg>
  );
}
export function CopyButton({
  value,
  label,
  text,
}: {
  value: string;
  label: string;
  text?: string;
}) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1400);
    return () => clearTimeout(timer);
  }, [copied]);
  const copy = () => {
    navigator.clipboard
      ?.writeText(value)
      .then(() => setCopied(true))
      .catch(() => undefined);
  };
  if (text)
    return (
      <button type="button" className="secondary" onClick={copy}>
        <Icon name={copied ? "check" : "copy"} size={14} />
        {copied ? "Copied" : text}
      </button>
    );
  return (
    <button
      type="button"
      className="icon-button"
      aria-label={`Copy ${label}`}
      title={copied ? "Copied" : `Copy ${label}`}
      onClick={copy}
    >
      <Icon name={copied ? "check" : "copy"} size={14} />
    </button>
  );
}
export const short = (value: string) =>
  value.length > 14 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
export function ShortId({
  value,
  label = "ID",
  testId,
  copy = true,
}: {
  value: string;
  label?: string;
  testId?: string;
  copy?: boolean;
}) {
  return (
    <span className="id-copy">
      <code className="hash" title={value}>
        <span aria-hidden="true">{short(value)}</span>
        <span className="sr-only" data-testid={testId}>
          {value}
        </span>
      </code>
      {copy && <CopyButton value={value} label={label} />}
    </span>
  );
}
const QUOTES = ["USDT", "USDC", "FDUSD", "BUSD", "EUR", "BTC", "ETH"];
export function splitPair(symbol: string): [string, string] {
  const quote = QUOTES.find(
    (q) => symbol.endsWith(q) && symbol.length > q.length,
  );
  return quote ? [symbol.slice(0, -quote.length), quote] : [symbol, ""];
}
export const pairText = (symbol: string) => {
  const [base, quote] = splitPair(symbol);
  return quote ? `${base}/${quote}` : base;
};
export const SERIES = ["#f5f5f5", "#a5a5ac", "#8da9c4", "#566f88"];
export function Pair({
  symbol,
  series = 0,
  small,
}: {
  symbol: string;
  series?: number;
  small?: boolean;
}) {
  const [base, quote] = splitPair(symbol);
  return (
    <span className={small ? "pair small" : "pair"}>
      <i
        className="pair-mark"
        aria-hidden="true"
        style={{ background: SERIES[series % SERIES.length] }}
      />
      <span>
        {base}
        {quote && <span className="quote">/{quote}</span>}
      </span>
    </span>
  );
}
export const venueName = (venue: unknown) =>
  typeof venue === "string" && venue
    ? venue
        .split("_")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ")
    : "";
/** Exact decimal text with its tail dimmed: trailing zeros, or digits past `digits`. */
export function Exact({ value, digits }: { value: unknown; digits?: number }) {
  const text = String(value);
  const decimal = /^(-?\d+)\.\d+$/.exec(text);
  if (!decimal) return <span className="exact">{text}</span>;
  let cut = text.length;
  if (digits !== undefined)
    cut = Math.min(text.length, decimal[1].length + 1 + digits);
  else {
    const zeros = /\.?0+$/.exec(text);
    if (zeros) cut = zeros.index;
  }
  return (
    <span className="exact">
      {text.slice(0, cut)}
      {cut < text.length && <span className="dim">{text.slice(cut)}</span>}
    </span>
  );
}
/** Decimal text without trailing zeros, for compact labels; the value is unchanged. */
export const trimmed = (value: unknown) => {
  const text = String(value);
  return /^-?\d+\.\d+$/.test(text) ? text.replace(/\.?0+$/, "") : text;
};
export function Figure({
  label,
  unit,
  value,
  note,
  lead,
  tone,
}: {
  label: string;
  unit?: string;
  value: ReactNode;
  note?: ReactNode;
  lead?: boolean;
  tone?: string;
}) {
  return (
    <div className={lead ? "figure lead" : "figure"}>
      <div className="label">
        <span>{label}</span>
        {unit && <span>{unit}</span>}
      </div>
      <div className={tone ? `value ${tone}` : "value"}>{value}</div>
      {note && <div className="note">{note}</div>}
    </div>
  );
}
export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}
const MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");
const pad = (n: number) => String(n).padStart(2, "0");
function parts(iso: string) {
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return null;
  return {
    day: d.getUTCDate(),
    month: MONTHS[d.getUTCMonth()],
    year: d.getUTCFullYear(),
    time: `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`,
  };
}
/** "29 Jan" */
export function dayLabel(iso: string) {
  const p = parts(iso);
  return p ? `${p.day} ${p.month}` : iso;
}
/** "29 Jan 19:00" */
export function minuteLabel(iso: string) {
  const p = parts(iso);
  return p ? `${p.day} ${p.month} ${p.time}` : iso;
}
/** "27 Oct 2026, 22:59 UTC" */
export function stamp(iso: string) {
  const p = parts(iso);
  return p ? `${p.day} ${p.month} ${p.year}, ${p.time} UTC` : iso;
}
/** "29–31 Jan" or "29 Dec – 2 Jan", from inclusive UTC dates. */
export function dayRange(first: string, last: string, year = false) {
  const a = parts(first);
  const b = parts(last);
  if (!a || !b) return `${first} to ${last}`;
  const tail = year ? ` ${b.year}` : "";
  if (first.slice(0, 10) === last.slice(0, 10))
    return `${b.day} ${b.month}${tail}`;
  if (a.month === b.month && a.year === b.year)
    return `${a.day}–${b.day} ${b.month}${tail}`;
  return `${a.day} ${a.month}${year && a.year !== b.year ? ` ${a.year}` : ""} – ${b.day} ${b.month}${tail}`;
}
export function duration(ms: number) {
  if (!Number.isFinite(ms) || ms < 0) return "";
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const minutes = Math.round(ms / 60_000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 72)
    return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
  const days = Math.floor(hours / 24);
  return hours % 24 ? `${days} d ${hours % 24} h` : `${days} d`;
}
const WORKERS: Record<
  string,
  {
    waiting: string;
    running: string;
    command: (id: string, jobs: number) => string;
  }
> = {
  research: {
    waiting: "Waiting for a research worker",
    running: "Running on a research worker",
    command: (id) =>
      `python -m marketlab.research_cli worker --max-runs 1 --run ${id}`,
  },
  memo: {
    waiting: "Waiting for an inference worker",
    running: "Writing the memo",
    command: () => "python -m marketlab.inference_cli worker --max-jobs 1",
  },
  copilot: {
    waiting: "Waiting for a copilot worker",
    running: "Interpreting the request",
    command: (id) =>
      `python -m marketlab.copilot_cli worker --max-jobs 1 --request ${id}`,
  },
  ingestion: {
    waiting: "Waiting for an ingestion worker",
    running: "Ingesting daily archives",
    command: (id, jobs) =>
      `python -m marketlab.dataset_cli worker --max-jobs ${jobs} --submission ${id}`,
  },
};
/** Queued work is only described: the workspace never starts a worker itself. */
export function WorkerHint({
  kind,
  id = "",
  jobs = 1,
  since,
  running,
}: {
  kind: keyof typeof WORKERS;
  id?: string;
  jobs?: number;
  since?: string;
  running?: boolean;
}) {
  const worker = WORKERS[kind];
  const command = worker.command(id, jobs);
  return (
    <section className="worker">
      <div>
        <h2>
          <Spinner />
          {running ? worker.running : worker.waiting}
          {since && !running && (
            <span className="muted">queued {minuteLabel(since)} UTC</span>
          )}
        </h2>
        {!running && (
          <>
            <code>
              <span className="prompt" aria-hidden="true">
                ${" "}
              </span>
              {command}
            </code>
            <p className="muted">
              Run it from the project directory. It exits when the work is done.
            </p>
          </>
        )}
      </div>
      {!running && (
        <CopyButton
          value={command}
          label="worker command"
          text="Copy command"
        />
      )}
    </section>
  );
}
/** Short run name for lists: "BTC profile", "BTC vs ETH", "BTC clusters". */
export function runName(run: Data) {
  const bases = ((run.symbols ?? run.spec?.symbols ?? []) as string[]).map(
    (s) => splitPair(s)[0],
  );
  const workflow = run.workflow ?? run.spec?.workflow;
  if (workflow === "cross_asset") return bases.join(" vs ") || "Cross-asset";
  if (workflow === "volatility_cluster")
    return `${bases[0] ?? ""} clusters`.trim();
  return `${bases[0] ?? ""} profile`.trim();
}
