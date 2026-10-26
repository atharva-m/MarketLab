import { type ReactNode } from "react";
import { useRoute } from "./hooks";
import { Catalog, JobList } from "./Catalog";
import {
  ResearchForm,
  Ingestion,
  IngestionDetail,
  ResearchDetail,
  CopilotForm,
  CopilotDetail,
} from "./Pages";
export default function App() {
  const route = useRoute();
  let content: ReactNode;
  const [family, id] = route.split("/").filter(Boolean);
  if (route === "/research/new") content = <ResearchForm />;
  else if (route === "/ingestion/new") content = <Ingestion />;
  else if (route === "/copilot/new") content = <CopilotForm />;
  else if (family === "runs" && /^[a-f0-9-]{36}$/.test(id ?? ""))
    content = <ResearchDetail key={id} id={id} />;
  else if (family === "ingestion" && /^[a-f0-9-]{36}$/.test(id ?? ""))
    content = <IngestionDetail key={id} id={id} />;
  else if (family === "copilot" && /^[a-f0-9-]{36}$/.test(id ?? ""))
    content = <CopilotDetail key={id} id={id} />;
  else if (route === "/jobs") content = <JobList />;
  else content = <Catalog />;
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
      <aside>
        <a className="brand" href="#/catalog">
          <span className="brand-mark">M</span>MarketLab
        </a>
        <p className="sidebar-caption">LOCAL RESEARCH WORKSPACE</p>
        <nav aria-label="Main navigation">
          {[
            ["/catalog", "◫", "Dataset catalog"],
            ["/ingestion/new", "↓", "Ingestion"],
            ["/jobs", "≡", "Jobs & submissions"],
            ["/research/new", "⌁", "Manual research"],
            ["/copilot/new", "✧", "Copilot"],
          ].map(([href, icon, title]) => (
            <a
              key={href}
              href={`#${href}`}
              aria-current={route === href ? "page" : undefined}
            >
              <span aria-hidden>{icon}</span>
              {title}
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="local-dot" /> Local / January 2025
          <p>
            Explicit data. Reproducible numbers.
            <br />
            Grounded generated memos.
          </p>
        </div>
      </aside>
      <div className="main-column">
        <div className="topbar">
          <span>RESEARCH / MARKET DATA</span>
          <span className="top-pill">BTC + ETH · Binance Spot</span>
        </div>
        <main id="main-content" tabIndex={-1} key={route}>
          {content}
        </main>
        <footer>
          MarketLab · descriptive research · UTC throughout · immutable
          registered artifacts
        </footer>
      </div>
    </div>
  );
}
