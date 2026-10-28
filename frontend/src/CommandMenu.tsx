import { useEffect, useRef, useState } from "react";
import { request, type Data } from "./client";
import { navigate } from "./hooks";
import { dayRange, Icon, runName, type IconName } from "./ui";
type Item = {
  key: string;
  group: string;
  label: string;
  hint?: string;
  id?: string;
  icon: IconName;
  tone?: string;
  path: string;
};
const PAGES: Item[] = [
  {
    key: "d",
    group: "Go to",
    label: "Datasets",
    hint: "G then D",
    icon: "datasets",
    path: "/catalog",
  },
  {
    key: "i",
    group: "Go to",
    label: "Ingestion",
    hint: "G then I",
    icon: "ingestion",
    path: "/ingestion/new",
  },
  {
    key: "j",
    group: "Go to",
    label: "Jobs",
    hint: "G then J",
    icon: "jobs",
    path: "/jobs",
  },
  {
    key: "n",
    group: "Go to",
    label: "New research",
    hint: "N",
    icon: "research",
    path: "/research/new",
  },
  {
    key: "c",
    group: "Go to",
    label: "Ask the copilot",
    hint: "G then C",
    icon: "copilot",
    path: "/copilot/new",
  },
];
const OPEN = "marketlab-command-menu";
export const openCommandMenu = (opener?: HTMLElement) =>
  window.dispatchEvent(new CustomEvent(OPEN, { detail: opener }));
const typing = (target: EventTarget | null) =>
  target instanceof HTMLElement &&
  (target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
function byId(query: string): Item[] {
  const value = query.trim().toLowerCase();
  if (
    /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value)
  )
    return [
      {
        key: "run",
        group: "Open by ID",
        label: "Open research run",
        icon: "run",
        path: `/runs/${value}`,
      },
      {
        key: "copilot",
        group: "Open by ID",
        label: "Open copilot request",
        icon: "copilot",
        path: `/copilot/${value}`,
      },
      {
        key: "ingestion",
        group: "Open by ID",
        label: "Open ingestion submission",
        icon: "ingestion",
        path: `/ingestion/${value}`,
      },
    ];
  if (/^[a-f0-9]{64}$/.test(value))
    return [
      {
        key: "version",
        group: "Open by ID",
        label: "Open dataset version",
        icon: "hash",
        path: `/catalog/${value}`,
      },
    ];
  return [];
}
export function CommandMenu() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const [runs, setRuns] = useState<Data[]>([]);
  const restore = useRef<Element | null>(null);
  useEffect(() => {
    let leader = 0;
    const key = (e: KeyboardEvent) => {
      if (
        (e.ctrlKey || e.metaKey) &&
        !e.altKey &&
        e.key.toLowerCase() === "k"
      ) {
        e.preventDefault();
        if (!document.querySelector(".command"))
          restore.current = document.activeElement;
        setOpen((v) => !v);
        return;
      }
      if (
        e.ctrlKey ||
        e.metaKey ||
        e.altKey ||
        typing(e.target) ||
        document.querySelector(".command")
      )
        return;
      const k = e.key.toLowerCase();
      if (Date.now() - leader < 1200) {
        leader = 0;
        const page = PAGES.find((p) => p.key === k && p.key !== "n");
        if (page) navigate(page.path);
      } else if (k === "g") leader = Date.now();
      else if (k === "n") navigate("/research/new");
    };
    const show = (event: Event) => {
      restore.current =
        event instanceof CustomEvent && event.detail instanceof HTMLElement
          ? event.detail
          : document.activeElement;
      setOpen(true);
    };
    window.addEventListener("keydown", key);
    window.addEventListener(OPEN, show);
    return () => {
      window.removeEventListener("keydown", key);
      window.removeEventListener(OPEN, show);
    };
  }, []);
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setIndex(0);
    const controller = new AbortController();
    request("/v1/research/runs?limit=6", { signal: controller.signal }).then(
      ({ data }) => setRuns((data.items ?? []) as Data[]),
      () => undefined,
    );
    return () => {
      controller.abort();
      if (restore.current instanceof HTMLElement) restore.current.focus();
    };
  }, [open]);
  useEffect(() => {
    document
      .getElementById(`command-${index}`)
      ?.scrollIntoView({ block: "nearest" });
  }, [index]);
  if (!open) return null;
  const text = query.trim().toLowerCase();
  const recent: Item[] = runs.map((run) => ({
    key: run.run_id,
    group: "Recent runs",
    label: runName(run),
    hint:
      run.start && run.end
        ? dayRange(run.start, new Date(Date.parse(run.end) - 1).toISOString())
        : undefined,
    id: String(run.run_id).slice(0, 8),
    icon: "run",
    tone:
      run.state === "succeeded"
        ? "up"
        : ["queued", "running", "retry_wait"].includes(run.state)
          ? "warn"
          : undefined,
    path: `/runs/${run.run_id}`,
  }));
  const items = [
    ...byId(query),
    ...[...PAGES, ...recent].filter(
      (item) =>
        !text ||
        item.label.toLowerCase().includes(text) ||
        item.path.includes(text),
    ),
  ];
  const selected = Math.min(index, Math.max(0, items.length - 1));
  const close = () => setOpen(false);
  const choose = (item: Item | undefined) => {
    if (!item) return;
    restore.current = null;
    setOpen(false);
    navigate(item.path);
  };
  const groups = [...new Set(items.map((item) => item.group))];
  return (
    <div
      className="command-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        className="command"
        role="dialog"
        aria-modal="true"
        aria-label="Command menu"
        onKeyDown={(e) => {
          if (e.key === "Escape") close();
          else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            const step = e.key === "ArrowDown" ? 1 : -1;
            setIndex(
              (selected + step + items.length) % Math.max(1, items.length),
            );
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(items[selected]);
          } else if (e.key === "Tab") e.preventDefault();
        }}
      >
        <div className="command-input">
          <Icon name="search" />
          <input
            autoFocus
            role="combobox"
            aria-label="Search commands"
            aria-expanded="true"
            aria-controls="command-list"
            aria-activedescendant={
              items.length ? `command-${selected}` : undefined
            }
            placeholder="Search pages and runs, or paste an ID"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setIndex(0);
            }}
          />
          <kbd>Esc</kbd>
        </div>
        <div
          className="command-list"
          id="command-list"
          role="listbox"
          aria-label="Commands"
        >
          {groups.map((group) => (
            <div role="group" aria-label={group} key={group}>
              <div className="command-group" aria-hidden="true">
                {group}
              </div>
              {items.map((item, i) =>
                item.group === group ? (
                  <div
                    key={`${item.group}${item.key}`}
                    id={`command-${i}`}
                    role="option"
                    aria-selected={i === selected}
                    className="command-item"
                    onMouseMove={() => i !== selected && setIndex(i)}
                    onClick={() => choose(item)}
                  >
                    <span
                      className={
                        item.tone ? `app-icon ${item.tone}` : "app-icon"
                      }
                    >
                      <Icon name={item.icon} size={14} />
                    </span>
                    <span className="label">{item.label}</span>
                    {item.hint && <span className="hint">{item.hint}</span>}
                    {item.id && <code className="hint">{item.id}</code>}
                  </div>
                ) : null,
              )}
            </div>
          ))}
          {!items.length && <p className="command-empty">No matches</p>}
        </div>
        <div className="command-foot" aria-hidden="true">
          <span>
            <kbd>↑</kbd> <kbd>↓</kbd> move
          </span>
          <span>
            <kbd>Enter</kbd> open
          </span>
          <span>
            <kbd>Esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}
