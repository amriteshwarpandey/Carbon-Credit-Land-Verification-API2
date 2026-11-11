import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../hooks";
import PlotMap from "../components/PlotMap";
import { ErrorMsg, Loading, fmtDate } from "../components/ui";

function AddPlot({ farmerId, onDone }) {
  const [form, setForm] = useState({ name: "", crop_type: "", acreage: "" });
  const [pos, setPos] = useState(null);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (!pos) return setError(new Error("Click the map to set the plot location."));
    setError(null);
    try {
      await api.createPlot(farmerId, {
        name: form.name,
        crop_type: form.crop_type,
        acreage: Number(form.acreage),
        latitude: pos.lat,
        longitude: pos.lon,
      });
      setForm({ name: "", crop_type: "", acreage: "" });
      setPos(null);
      onDone();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h3>Register a plot</h3>
      <div className="row">
        <label>Name<input value={form.name} onChange={set("name")} required /></label>
        <label>Crop<input value={form.crop_type} onChange={set("crop_type")} required /></label>
        <label>
          Acreage
          <input type="number" min="0.01" step="any" value={form.acreage} onChange={set("acreage")} required />
        </label>
      </div>
      <p className="muted">
        Location: {pos ? `${pos.lat.toFixed(5)}, ${pos.lon.toFixed(5)}` : "click the map to place the plot"}
      </p>
      <PlotMap point={pos} onPick={(lat, lon) => setPos({ lat, lon })} />
      <ErrorMsg error={error} />
      <button>Register plot</button>
    </form>
  );
}

export default function FarmerDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const farmer = useAsync(() => api.farmer(id), [id]);
  const plots = useAsync(() => api.plots(id), [id]);
  const ledger = useAsync(() => api.ledger(id), [id]);

  if (farmer.loading || farmer.error) return <Loading state={farmer} />;
  const f = farmer.data;

  return (
    <>
      <p><Link to="/farmers">← Farmers</Link></p>
      <h2>{f.name}</h2>
      <p className="muted">{[f.village, f.phone].filter(Boolean).join(" · ") || "No contact details"}</p>

      <h3>Payout ledger</h3>
      <Loading state={ledger} />
      {ledger.data && (
        <>
          <div className="stats">
            <div><b>{ledger.data.total_co2e_tonnes}</b><span>tCO₂e credited</span></div>
            <div><b>${ledger.data.total_amount_usd}</b><span>payout total</span></div>
          </div>
          {!!ledger.data.entries.length && (
            <table>
              <thead><tr><th>Entry</th><th>Intervention</th><th>tCO₂e</th><th>USD</th><th>Status</th><th>Created</th></tr></thead>
              <tbody>
                {ledger.data.entries.map((e) => (
                  <tr key={e.id}>
                    <td>{e.id}</td><td>#{e.intervention_id}</td><td>{e.co2e_tonnes}</td>
                    <td>${e.amount_usd}</td><td>{e.status}</td><td>{fmtDate(e.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <h3>Plots</h3>
      <Loading state={plots} />
      {plots.data && (
        <table>
          <thead><tr><th>Name</th><th>Crop</th><th>Acres</th><th>Location</th></tr></thead>
          <tbody>
            {plots.data.map((p) => (
              <tr key={p.id}>
                <td><Link to={`/plots/${p.id}`}>{p.name}</Link></td>
                <td>{p.crop_type}</td><td>{p.acreage}</td>
                <td>{p.latitude.toFixed(4)}, {p.longitude.toFixed(4)}</td>
              </tr>
            ))}
            {!plots.data.length && <tr><td colSpan="4" className="muted">No plots registered.</td></tr>}
          </tbody>
        </table>
      )}
      {user.role !== "auditor" && <AddPlot farmerId={id} onDone={plots.reload} />}
    </>
  );
}
