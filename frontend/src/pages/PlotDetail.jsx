import { Fragment, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../hooks";
import PlotMap from "../components/PlotMap";
import { EvidencePanel, NdviPanel } from "../components/LogDetails";
import { ErrorMsg, Loading, PRACTICE_LABEL, PRACTICE_UNIT, StatusBadge, fmtDate } from "../components/ui";

const today = () => new Date().toISOString().slice(0, 10);

function Weather({ plotId }) {
  const [requested, setRequested] = useState(false);
  const w = useAsync(() => (requested ? api.weather(plotId) : Promise.resolve(null)), [plotId, requested]);
  if (!requested) return <button className="ghost" onClick={() => setRequested(true)}>Load weather &amp; soil data</button>;
  if (w.loading || w.error) return <Loading state={w} />;
  const s = w.data.summary;
  const n = (v, unit = "") => (v == null ? "—" : `${v}${unit}`);
  return (
    <>
      <div className="stats">
        <div><b>{n(s.total_precipitation_mm, " mm")}</b><span>total rainfall</span></div>
        <div><b>{n(s.precipitation_mm_day, " mm")}</b><span>avg per day</span></div>
        <div><b>{n(s.temperature_c, " °C")}</b><span>avg temperature</span></div>
        <div><b>{n(s.root_zone_soil_wetness)}</b><span>root-zone wetness (0–1)</span></div>
      </div>
      <p className="muted">{w.data.source} · {w.data.start} to {w.data.end}</p>
    </>
  );
}

function LogForm({ plotId, onDone }) {
  const [form, setForm] = useState({ practice: "no_till", quantity: "", performed_on: today(), notes: "" });
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const needsQty = form.practice in PRACTICE_UNIT;

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await api.createIntervention(plotId, {
        practice: form.practice,
        quantity: needsQty ? Number(form.quantity) : null,
        performed_on: form.performed_on,
        notes: form.notes || null,
      });
      setForm({ ...form, quantity: "", notes: "" });
      onDone();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h3>Log an intervention</h3>
      <div className="row">
        <label>
          Practice
          <select value={form.practice} onChange={set("practice")}>
            {Object.entries(PRACTICE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        {needsQty && (
          <label>
            Quantity ({PRACTICE_UNIT[form.practice]})
            <input type="number" min="0" step="any" value={form.quantity} onChange={set("quantity")} required />
          </label>
        )}
        <label>Performed on<input type="date" value={form.performed_on} onChange={set("performed_on")} required /></label>
      </div>
      <label>Notes<textarea rows="2" value={form.notes} onChange={set("notes")} /></label>
      <ErrorMsg error={error} />
      <button>Submit for review</button>
    </form>
  );
}

export default function PlotDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const plot = useAsync(() => api.plot(id), [id]);
  const logs = useAsync(() => api.plotInterventions(id), [id]);
  const [certError, setCertError] = useState(null);
  const [open, setOpen] = useState(new Set());
  const toggle = (id) =>
    setOpen((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  if (plot.loading || plot.error) return <Loading state={plot} />;
  const p = plot.data;

  const openCert = async (logId, format) => {
    setCertError(null);
    try {
      await api.openCertificate(logId, format);
    } catch (err) {
      setCertError(err);
    }
  };

  return (
    <>
      <p><Link to={`/farmers/${p.farmer_id}`}>← Farmer #{p.farmer_id}</Link></p>
      <h2>{p.name}</h2>
      <p className="muted">{p.crop_type} · {p.acreage} acres · {p.latitude.toFixed(5)}, {p.longitude.toFixed(5)}</p>
      <PlotMap point={{ lat: p.latitude, lon: p.longitude }} geojson={p.geojson} />

      <h3>Weather &amp; soil</h3>
      <Weather plotId={id} />

      <h3>Interventions</h3>
      <Loading state={logs} />
      <ErrorMsg error={certError} />
      {logs.data && (
        <table>
          <thead><tr><th>ID</th><th>Practice</th><th>Qty</th><th>Date</th><th>Status</th><th>tCO₂e</th><th>Review notes</th><th>Certificate</th><th></th></tr></thead>
          <tbody>
            {logs.data.map((l) => (
              <Fragment key={l.id}>
              <tr>
                <td>{l.id}</td>
                <td>{PRACTICE_LABEL[l.practice]}</td>
                <td>{l.quantity ?? "—"}</td>
                <td>{l.performed_on}</td>
                <td><StatusBadge status={l.status} /></td>
                <td>{l.co2e_tonnes ?? "—"}</td>
                <td>{l.review_notes || "—"}</td>
                <td>
                  {l.status === "approved" && l.processed_at ? (
                    <>
                      <button className="link" onClick={() => openCert(l.id, "pdf")}>PDF</button>{" · "}
                      <button className="link" onClick={() => openCert(l.id, "json")}>JSON</button>
                    </>
                  ) : l.status === "approved" ? <span className="muted">processing…</span> : "—"}
                </td>
                <td>
                  <button className="ghost" onClick={() => toggle(l.id)}>
                    {open.has(l.id) ? "Hide" : `Details (${l.evidence_count} files)`}
                  </button>
                </td>
              </tr>
              {open.has(l.id) && (
                <tr>
                  <td colSpan="9">
                    <EvidencePanel logId={l.id} canUpload={user.role !== "auditor" && l.status === "pending"} onChange={logs.reload} />
                    <NdviPanel logId={l.id} />
                    {l.methodology && <p className="muted">Methodology: {l.methodology}</p>}
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
            {!logs.data.length && <tr><td colSpan="9"className="muted">No interventions logged.</td></tr>}
          </tbody>
        </table>
      )}
      {user.role !== "auditor" && <LogForm plotId={id} onDone={logs.reload} />}
    </>
  );
}
