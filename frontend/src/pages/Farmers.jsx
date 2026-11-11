import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../hooks";
import { ErrorMsg, Loading } from "../components/ui";

export default function Farmers() {
  const { user } = useAuth();
  const farmers = useAsync(api.farmers, []);
  const canCreate = user.role !== "auditor";
  const [form, setForm] = useState({ name: "", phone: "", village: "" });
  const [error, setError] = useState(null);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await api.createFarmer({ name: form.name, phone: form.phone || null, village: form.village || null });
      setForm({ name: "", phone: "", village: "" });
      farmers.reload();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <>
      <h2>Farmers</h2>
      {canCreate && (
        <form className="card row" onSubmit={submit}>
          <label>Name<input value={form.name} onChange={set("name")} required /></label>
          <label>Phone<input value={form.phone} onChange={set("phone")} /></label>
          <label>Village<input value={form.village} onChange={set("village")} /></label>
          <button>Onboard farmer</button>
          <ErrorMsg error={error} />
        </form>
      )}
      <Loading state={farmers} />
      {farmers.data && (
        <table>
          <thead><tr><th>ID</th><th>Name</th><th>Village</th><th>Phone</th></tr></thead>
          <tbody>
            {farmers.data.map((f) => (
              <tr key={f.id}>
                <td>{f.id}</td>
                <td><Link to={`/farmers/${f.id}`}>{f.name}</Link></td>
                <td>{f.village || "—"}</td>
                <td>{f.phone || "—"}</td>
              </tr>
            ))}
            {!farmers.data.length && <tr><td colSpan="4" className="muted">No farmers yet.</td></tr>}
          </tbody>
        </table>
      )}
    </>
  );
}
