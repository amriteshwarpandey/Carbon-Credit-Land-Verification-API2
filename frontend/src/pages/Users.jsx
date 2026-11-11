import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../hooks";
import { ErrorMsg, Loading } from "../components/ui";

function UserRow({ u, isSelf, onDone, onError }) {
  const act = (patch) => async () => {
    onError(null);
    try {
      await api.updateUser(u.id, patch);
      onDone();
    } catch (e) {
      onError(e);
    }
  };
  const reset = async () => {
    const password = window.prompt(`New password for ${u.email} (min 8 characters):`);
    if (password) await act({ password })();
  };

  return (
    <tr className={u.is_active ? undefined : "muted"}>
      <td>{u.email}{isSelf && " (you)"}</td>
      <td>{u.full_name || "—"}</td>
      <td>
        <select value={u.role} disabled={isSelf} onChange={(e) => act({ role: e.target.value })()}>
          <option value="field_agent">Field agent</option>
          <option value="auditor">Auditor</option>
          <option value="admin">Admin</option>
        </select>
      </td>
      <td>{u.is_active ? "Active" : "Deactivated"}</td>
      <td>
        <button className="ghost" onClick={reset}>Reset password</button>{" "}
        {!isSelf && (
          <button className={u.is_active ? "danger" : "ghost"} onClick={act({ is_active: !u.is_active })}>
            {u.is_active ? "Deactivate" : "Reactivate"}
          </button>
        )}
      </td>
    </tr>
  );
}

export default function Users() {
  const { user } = useAuth();
  const users = useAsync(api.users, []);
  const blank = { email: "", full_name: "", password: "", role: "field_agent" };
  const [form, setForm] = useState(blank);
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setCreated(null);
    try {
      setCreated(await api.createUser(form));
      setForm(blank);
      users.reload();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <>
      <h2>Users</h2>
      <Loading state={users} />
      <ErrorMsg error={error} />
      {users.data && (
        <table>
          <thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {users.data.map((u) => (
              <UserRow key={u.id} u={u} isSelf={u.id === user.id} onDone={users.reload} onError={setError} />
            ))}
          </tbody>
        </table>
      )}

      <h3>Create user</h3>
      <form className="card" onSubmit={submit}>
        <div className="row">
          <label>Email<input type="email" value={form.email} onChange={set("email")} required /></label>
          <label>Full name<input value={form.full_name} onChange={set("full_name")} /></label>
          <label>
            Password (min 8)
            <input type="password" minLength={8} value={form.password} onChange={set("password")} required />
          </label>
          <label>
            Role
            <select value={form.role} onChange={set("role")}>
              <option value="field_agent">Field agent</option>
              <option value="auditor">Auditor</option>
              <option value="admin">Admin</option>
            </select>
          </label>
        </div>
        {created && <p className="ok">Created {created.email} ({created.role}).</p>}
        <button>Create user</button>
      </form>
    </>
  );
}
