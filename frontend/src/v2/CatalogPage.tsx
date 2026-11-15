import { useEffect, useState } from "react";
import { DataView, ErrorBox, PageTitle } from "../components";
import { dayLabel, dayRange, ShortId } from "../ui";
import { type Dataset } from "./api";
import { errorText, useV2 } from "./hooks";
import { saveSelection, selected } from "./state";
import {
  EmptyState,
  Field,
  InstrumentChoice,
  InstrumentPages,
  InstrumentPill,
  Status,
  instrumentMap,
  query,
  seriesOf,
  symbolOf,
  useInstruments,
} from "./parts";

export function Catalog() {
  const instruments = useInstruments();
  const [filter, setFilter] = useState({
    instrument_id: "",
    from_date: "",
    before_date: "",
  });
  const [applied, setApplied] = useState<Record<string, string>>({});
  const [cursor, setCursor] = useState("");
  const catalog = useV2(
    `/v2/datasets?${query({ ...applied, limit: "25", cursor })}`,
  );
  const [pins, setPins] = useState(selected);
  const [error, setError] = useState("");
  const [inspect, setInspect] = useState("");
  const detail = useV2(inspect ? `/v2/datasets/${inspect}` : null);
  const rows = (catalog.data?.items ?? []) as Dataset[];
  const byId = instrumentMap(instruments.rows);
  const rowIds = rows.map((row) => row.instrument_id);
  const picked = [...pins].sort(
    (a, b) =>
      a.instrument_id.localeCompare(b.instrument_id) ||
      a.trade_date.localeCompare(b.trade_date),
  );
  const pickedDates = picked.map((v) => v.trade_date).sort();
  const pickedSymbols = [
    ...new Set(picked.map((v) => symbolOf(v.instrument_id))),
  ];
  const toggle = (row: Dataset, checked: boolean) => {
    try {
      const next = checked
        ? [...pins, row]
        : pins.filter((v) => v.dataset_version_id !== row.dataset_version_id);
      saveSelection(next);
      setPins(next);
      setError("");
    } catch (e) {
      setError(errorText(e));
    }
  };
  useEffect(() => {
    if (
      instruments.data &&
      !instruments.cursor &&
      instruments.rows.length === 1 &&
      !instruments.data.next_cursor
    )
      setFilter((v) =>
        v.instrument_id
          ? v
          : { ...v, instrument_id: instruments.rows[0].instrument_id },
      );
  }, [instruments.data]); // The response, not current selection, determines uniqueness.
  return (
    <>
      <PageTitle title="Catalog">
        <div className="title-actions">
          <button
            type="button"
            className="secondary"
            onClick={() => catalog.refresh()}
          >
            Refresh
          </button>
        </div>
      </PageTitle>
      <form
        className="panel controls"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(filter);
          setCursor("");
        }}
      >
        <InstrumentChoice
          rows={instruments.rows}
          value={filter.instrument_id}
          required={false}
          placeholder="All instruments"
          onChange={(v) => setFilter({ ...filter, instrument_id: v })}
        />
        <Field
          title="From"
          type="date"
          value={filter.from_date}
          required={false}
          change={(v) => setFilter({ ...filter, from_date: v })}
        />
        <Field
          title="Before"
          type="date"
          value={filter.before_date}
          required={false}
          change={(v) => setFilter({ ...filter, before_date: v })}
        />
        <button className="secondary">Apply</button>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setFilter({ instrument_id: "", from_date: "", before_date: "" });
            setApplied({});
            setCursor("");
          }}
        >
          Reset
        </button>
      </form>
      <InstrumentPages result={instruments} />
      <ErrorBox>{catalog.error || error}</ErrorBox>
      {catalog.busy && <Status>Loading…</Status>}
      {catalog.data && !rows.length && (
        <EmptyState
          title="No datasets yet"
          text="Add an instrument, then ingest or import its trades."
        >
          <a className="button secondary" href="#/v2/instruments">
            Add an instrument
          </a>
          <a className="button secondary" href="#/v2/ingestion/new">
            Ingest archives
          </a>
          <a className="button secondary" href="#/v2/imports/new">
            Import a file
          </a>
        </EmptyState>
      )}
      {!!rows.length && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>
                  <span className="sr-only">Pin</span>
                </th>
                <th>Instrument</th>
                <th>Day</th>
                <th className="num">Trades</th>
                <th>Version</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.contract}/${row.dataset_version_id}`}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Pin ${row.instrument_id} ${row.trade_date} ${row.dataset_version_id}`}
                      checked={pins.some(
                        (v) => v.dataset_version_id === row.dataset_version_id,
                      )}
                      onChange={(e) => toggle(row, e.target.checked)}
                    />
                  </td>
                  <td>
                    <InstrumentPill
                      small
                      id={row.instrument_id}
                      instrument={byId.get(row.instrument_id)}
                      series={seriesOf(rowIds, row.instrument_id)}
                    />
                  </td>
                  <td>{row.trade_date}</td>
                  <td className="num">{String(row.row_count)}</td>
                  <td>
                    <ShortId
                      value={row.dataset_version_id}
                      label="dataset version"
                    />
                  </td>
                  <td className="num">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setInspect(row.dataset_version_id)}
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(catalog.data?.next_cursor || cursor) && (
        <div className="pagination">
          {cursor ? (
            <button
              type="button"
              className="secondary"
              onClick={() => setCursor("")}
            >
              First page
            </button>
          ) : (
            <span />
          )}
          {catalog.data?.next_cursor && (
            <button
              type="button"
              className="secondary"
              onClick={() => setCursor(catalog.data!.next_cursor)}
            >
              Next page
            </button>
          )}
        </div>
      )}
      <section className="selection" aria-label="Selection">
        <div>
          {picked.length ? (
            <>
              <div className="summary-line">
                <strong data-testid="pin-count">
                  {picked.length} of 62 pinned
                </strong>
                <span className="muted">{pickedSymbols.join(", ")}</span>
                <span className="muted">
                  {dayRange(
                    pickedDates[0],
                    pickedDates[pickedDates.length - 1],
                  )}
                </span>
              </div>
              <div className="chips">
                {picked.slice(0, 8).map((v) => (
                  <span className="chip" key={v.dataset_version_id}>
                    {symbolOf(v.instrument_id)} {dayLabel(v.trade_date)}
                  </span>
                ))}
                {picked.length > 8 && (
                  <span className="chip">+{picked.length - 8} more</span>
                )}
              </div>
            </>
          ) : (
            <>
              <strong data-testid="pin-count" className="sr-only">
                0 of 62 pinned
              </strong>
              <span className="muted">
                Pin versions in the table to use them in research.
              </span>
            </>
          )}
        </div>
        <div className="actions">
          <button
            type="button"
            className="secondary"
            disabled={!picked.length}
            onClick={() => {
              saveSelection([]);
              setPins([]);
            }}
          >
            Clear
          </button>
          {!!picked.length && (
            <>
              <a className="button secondary" href="#/v2/copilot/new">
                Ask copilot
              </a>
              <a className="button" href="#/v2/research/new">
                Run research
              </a>
            </>
          )}
        </div>
      </section>
      {inspect && (
        <section className="panel">
          <div className="toolbar">
            <h2>
              Version <ShortId value={inspect} label="dataset version" />
            </h2>
            <button
              type="button"
              className="secondary"
              onClick={() => setInspect("")}
            >
              Close
            </button>
          </div>
          <ErrorBox>{detail.error}</ErrorBox>
          {detail.data && <DataView data={detail.data} />}
        </section>
      )}
    </>
  );
}
