import { useState } from "react";
import { ErrorBox, PageTitle, Tag } from "../components";
import { mutate, type Instrument } from "./api";
import { useAction } from "./hooks";
import {
  Field,
  InstrumentPages,
  InstrumentPill,
  idPath,
  useInstruments,
} from "./parts";

const FIELDS: [keyof typeof EMPTY, string, string][] = [
  ["source_symbol", "Symbol", "SOLUSDT"],
  ["base_asset", "Base asset", "SOL"],
  ["quote_asset", "Quote asset", "USDT"],
  ["display_name", "Display name", "Solana"],
];
const EMPTY = {
  source_symbol: "",
  base_asset: "",
  quote_asset: "",
  display_name: "",
};

export function Registry() {
  const instruments = useInstruments();
  const action = useAction();
  const [form, setForm] = useState(EMPTY);
  const [verified, setVerified] = useState(false);
  const [editing, setEditing] = useState<Instrument | null>(null);
  const [display, setDisplay] = useState("");
  return (
    <>
      <PageTitle title="Instruments" />
      <ErrorBox>{action.error || instruments.error}</ErrorBox>
      <div className="table-wrap">
        <table>
          <caption>Instruments</caption>
          <thead>
            <tr>
              <th>Instrument</th>
              <th>Symbol</th>
              <th>ID</th>
              <th>Status</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {instruments.rows.map((row) => (
              <tr key={row.instrument_id}>
                <td>
                  <InstrumentPill
                    small
                    id={row.instrument_id}
                    instrument={row}
                  />{" "}
                  <span className="muted">{row.display_name}</span>
                </td>
                <td>{row.source_symbol}</td>
                <td>
                  <code className="muted">{row.instrument_id}</code>
                </td>
                <td>
                  <Tag value={row.enabled ? "active" : "read_only"} />
                </td>
                <td className="num">
                  <button
                    type="button"
                    className="secondary"
                    disabled={action.busy}
                    onClick={() => {
                      setEditing(row);
                      setDisplay(row.display_name);
                    }}
                  >
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <InstrumentPages result={instruments} />
      {editing && (
        <form
          className="panel"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              await mutate(
                `registry-edit-${editing.instrument_id}-${editing.revision}`,
                `/v2/instruments/${idPath(editing.instrument_id)}`,
                {
                  display_name: display,
                  enabled: editing.enabled,
                  expected_revision: editing.revision,
                },
                "PATCH",
              );
              setEditing(null);
              instruments.refresh();
            });
          }}
        >
          <h2>Edit {editing.source_symbol}</h2>
          <Field title="Display name" value={display} change={setDisplay} />
          <label className="check">
            <input
              type="checkbox"
              checked={editing.enabled}
              onChange={(e) =>
                setEditing({ ...editing, enabled: e.target.checked })
              }
            />
            Accept new data
          </label>
          <div className="actions">
            <button disabled={action.busy}>Save</button>
            <button
              type="button"
              className="secondary"
              onClick={() => setEditing(null)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      <form
        className="panel"
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            if (!verified)
              throw new Error(
                "Confirm you checked these values against Binance.",
              );
            await mutate("registry-create", "/v2/instruments", {
              venue_id: "binance",
              market: "spot",
              ...form,
              trade_id_order: "numeric",
              adapter: "binance_daily",
            });
            instruments.refresh();
          });
        }}
      >
        <h2>Add instrument</h2>
        <div className="fields">
          {FIELDS.map(([name, title, placeholder]) => (
            <Field
              key={name}
              title={title}
              placeholder={placeholder}
              value={form[name]}
              change={(v) => setForm({ ...form, [name]: v })}
            />
          ))}
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={verified}
            onChange={(e) => setVerified(e.target.checked)}
          />
          Checked against Binance spot listings
        </label>
        <div className="actions">
          <button disabled={action.busy}>Add instrument</button>
        </div>
      </form>
    </>
  );
}
