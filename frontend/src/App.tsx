import { Fragment, useEffect, useState, type ReactNode } from "react";
import { request, type Data } from "./client";
import { useRoute } from "./hooks";
import { Catalog, JobList } from "./Catalog";
import { CommandMenu, openCommandMenu } from "./CommandMenu";
import {
  ResearchForm,
  Ingestion,
  IngestionDetail,
  CopilotForm,
  CopilotDetail,
} from "./Pages";
import { ResearchDetail } from "./Run";
import { Icon, runName, type IconName } from "./ui";
const WORDMARK = [
  "█▀▄▀█ ▄▀█ █▀█ █▄▀ █▀▀ ▀█▀ █   ▄▀█ █▄▄",
  "█ ▀ █ █▀█ █▀▄ █ █ ██▄  █  █▄▄ █▀█ █▄█",
].join("\n");
const NAV: [string, IconName, string][] = [
  ["/catalog", "datasets", "Datasets"],
  ["/ingestion/new", "ingestion", "Ingestion"],
  ["/jobs", "jobs", "Jobs"],
  ["/research/new", "research", "Research"],
  ["/copilot/new", "copilot", "Copilot"],
];
const SECTIONS: Record<string, [string, string]> = {
  catalog: ["datasets", "/catalog"],
  ingestion: ["ingestion", "/ingestion/new"],
  jobs: ["jobs", "/jobs"],
  research: ["research", "/research/new"],
  runs: ["runs", "/jobs"],
  copilot: ["copilot", "/copilot/new"],
};
const section = (family: string) =>
  family === "runs" || family === "research"
    ? "/research/new"
    : (SECTIONS[family]?.[1] ?? "/catalog");
const uuid = /^[a-f0-9-]{36}$/;
function RecentRuns({ route }: { route: string }) {
  const [runs, setRuns] = useState<Data[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    request("/v1/research/runs?limit=6", { signal: controller.signal }).then(
      ({ data }) => setRuns((data.items ?? []) as Data[]),
      () => undefined,
    );
    return () => controller.abort();
  }, [route]);
  if (!runs.length) return null;
  return (
    <nav className="recent" aria-label="Recent runs">
      <h2>Recent runs</h2>
      {runs.map((run) => (
        <a
          key={run.run_id}
          href={`#/runs/${run.run_id}`}
          aria-current={route === `/runs/${run.run_id}` ? "page" : undefined}
        >
          <span className={`state-mark ${run.state}`} aria-hidden="true" />
          <span className="label">{runName(run)}</span>
          <code className="id">{String(run.run_id).slice(0, 8)}</code>
        </a>
      ))}
    </nav>
  );
}
export default function App() {
  const route = useRoute();
  let content: ReactNode;
  const [family = "catalog", id] = route.split("/").filter(Boolean);
  if (route === "/research/new") content = <ResearchForm />;
  else if (route === "/ingestion/new") content = <Ingestion />;
  else if (route === "/copilot/new") content = <CopilotForm />;
  else if (family === "runs" && uuid.test(id ?? ""))
    content = <ResearchDetail key={id} id={id} />;
  else if (family === "ingestion" && uuid.test(id ?? ""))
    content = <IngestionDetail key={id} id={id} />;
  else if (family === "copilot" && uuid.test(id ?? ""))
    content = <CopilotDetail key={id} id={id} />;
  else if (route === "/jobs") content = <JobList />;
  else
    content = (
      <Catalog
        inspect={
          family === "catalog" && /^[a-f0-9]{64}$/.test(id ?? "") ? id : ""
        }
      />
    );
  const known = SECTIONS[family] ? family : "catalog";
  const crumbs: [string, string?][] = [
    ["marketlab", "/catalog"],
    [SECTIONS[known][0], id ? SECTIONS[known][1] : undefined],
  ];
  if (id && known === family)
    crumbs.push([id === "new" ? "new" : id.slice(0, 8)]);
  const current = section(known);
  return (
    <div className="workspace">
      <button
        className="skip"
        type="button"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        Skip to content
      </button>
      <aside className="sidebar">
        <a className="wordmark" href="#/catalog" aria-label="MarketLab home">
          <pre className="holo" aria-hidden="true">
            {WORDMARK}
          </pre>
        </a>
        <nav className="nav" aria-label="Main navigation">
          {NAV.map(([href, icon, title]) => (
            <a
              key={href}
              href={`#${href}`}
              className={current === href ? "active" : undefined}
              aria-current={route === href ? "page" : undefined}
            >
              <Icon name={icon} />
              {title}
            </a>
          ))}
        </nav>
        <RecentRuns route={route} />
      </aside>
      <div className="main-column">
        <div className="topbar">
          <nav className="crumbs" aria-label="Breadcrumb">
            {crumbs.map(([text, href], i) => (
              <Fragment key={i}>
                {i > 0 && <span aria-hidden="true">/</span>}
                {href && i < crumbs.length - 1 ? (
                  <a href={`#${href}`}>{text}</a>
                ) : (
                  <span className="here" aria-current="page">
                    {text}
                  </span>
                )}
              </Fragment>
            ))}
          </nav>
          <button type="button" className="jump" onClick={openCommandMenu}>
            <Icon name="search" size={14} />
            <span>Jump to…</span>
          </button>
        </div>
        <main id="main-content" tabIndex={-1} key={route}>
          {content}
        </main>
      </div>
      <CommandMenu />
    </div>
  );
}
