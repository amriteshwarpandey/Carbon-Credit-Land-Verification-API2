import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorMsg } from "../components/ui";

export default function Account() {
  const { user } = useAuth();
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (form.next !== form.confirm) return setError(new Error("New passwords do not match"));
    try {
      await api.changePassword(form.current, form.next);
      setForm({ current: "", next: "", confirm: "" });
      setDone(true);
    } catch (err) {
      setError(err);
    }
  };

  return (
    <>
      <h2>Account</h2>
      <p className="muted">{user.email}</p>
      <form className="card" onSubmit={submit} style={{ maxWidth: 420 }}>
        <h3>Change password</h3>
        <label>Current password<input type="password" value={form.current} onChange={set("current")} required /></label>
        <label>New password (min 8)<input type="password" minLength={8} value={form.next} onChange={set("next")} required /></label>
        <label>Confirm new password<input type="password" minLength={8} value={form.confirm} onChange={set("confirm")} required /></label>
        <ErrorMsg error={error} />
        {done && <p className="ok">Password updated.</p>}
        <button>Update password</button>
      </form>
    </>
  );
}
