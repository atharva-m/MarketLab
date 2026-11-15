import type { ReactNode } from "react";
import { DataView, ErrorBox } from "../components";
import { useV2 } from "./hooks";
import { Catalog } from "./CatalogPage";
import { Copilot } from "./Copilot";
import { Import } from "./ImportPage";
import { Official, Submission } from "./IngestionPages";
import { Registry } from "./RegistryPage";
import { Research } from "./ResearchPage";
import { Run } from "./RunPage";
import { Workers } from "./WorkersPage";
import "./workspace.css";

export { chartSegments } from "./RunPage";

/** Tab href, label and the route families that belong to its section. */
const TABS: [string, string, string[]][] = [
  ["/v2/catalog", "Catalog", ["catalog"]],
  ["/v2/research/new", "Research", ["research", "runs"]],
  ["/v2/copilot/new", "Copilot", ["copilot"]],
  ["/v2/ingestion/new", "Ingestion", ["ingestion", "submissions"]],
  ["/v2/imports/new", "Import", ["imports"]],
  ["/v2/instruments", "Instruments", ["instruments"]],
  ["/v2/workers", "Workers", ["workers"]],
];
/** The tab owning a `/v2/...` route; unknown routes fall back to Catalog. */
export function workspaceTab(route: string) {
  const family = route.split("/").filter(Boolean)[1];
  const [href, label] =
    TABS.find(([, , families]) => families.includes(family)) ?? TABS[0];
  return { href, label };
}
const uuid = /^[a-f0-9-]{36}$/;
export function V2Workspace({ route }: { route: string }) {
  const capabilities = useV2("/v2/capabilities");
  const parts = route.split("/").filter(Boolean);
  const [family, id] = parts.slice(1);
  const active = workspaceTab(route).href;
  let page: ReactNode;
  if (family === "research" && id === "new")
    page = <Research capabilities={capabilities.data} />;
  else if (
    family === "copilot" &&
    (id === "new" || /^[a-f0-9-]{36}$/.test(id ?? ""))
  )
    page = (
      <Copilot
        key={id}
        id={id === "new" ? undefined : id}
        available={capabilities.data?.copilot_available === true}
      />
    );
  else if (family === "runs" && uuid.test(id ?? ""))
    page = (
      <Run
        key={id}
        id={id}
        memoAvailable={capabilities.data?.memo_available === true}
      />
    );
  else if (family === "ingestion") page = <Official />;
  else if (family === "submissions" && uuid.test(id ?? ""))
    page = <Submission key={id} id={id} />;
  else if (family === "imports")
    page = <Import key={id ?? "new"} id={id !== "new" ? id : undefined} />;
  else if (family === "instruments") page = <Registry />;
  else if (family === "workers")
    page = (
      <Workers key={id ?? "all"} id={uuid.test(id ?? "") ? id : undefined} />
    );
  else page = <Catalog />;
  return (
    <div className="v2-workspace">
      <nav className="v2-tabs" aria-label="Workspace navigation">
        {TABS.map(([href, label]) => (
          <a
            key={href}
            href={`#${href}`}
            className={href === active ? "active" : undefined}
            aria-current={route === href ? "page" : undefined}
          >
            {label}
          </a>
        ))}
      </nav>
      <ErrorBox>{capabilities.error}</ErrorBox>
      {page}
      {capabilities.data && (
        <details className="provenance">
          <summary>Limits</summary>
          <DataView
            data={{
              ...capabilities.data.limits,
              copilot: capabilities.data.copilot_available
                ? "available"
                : "unavailable",
              memos: capabilities.data.memo_available
                ? "available"
                : "unavailable",
            }}
          />
        </details>
      )}
    </div>
  );
}
