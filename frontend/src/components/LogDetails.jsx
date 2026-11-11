import { useState } from "react";
import { api } from "../api";
import { useAsync } from "../hooks";
import { ErrorMsg, Loading } from "./ui";

const kb = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/** Evidence files for one intervention; agents/admins can upload while it is pending. */
export function EvidencePanel({ logId, canUpload, onChange }) {
  const files = useAsync(() => api.evidence(logId), [logId]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const open = async (id) => {
    setError(null);
    try {
      await api.openEvidence(logId, id);
    } catch (e) {
      setError(e);
    }
  };
  const upload = async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await api.uploadEvidence(logId, file);
      await files.reload();
      onChange?.();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <strong>Evidence</strong>
      <Loading state={files} />
      {files.data && !files.data.length && <p className="muted">No files attached.</p>}
      {files.data?.map((f) => (
        <div key={f.id}>
          <button className="link" onClick={() => open(f.id)}>{f.filename}</button>{" "}
          <span className="muted">({kb(f.size_bytes)}, sha256 {f.sha256.slice(0, 10)}…)</span>
        </div>
      ))}
      {canUpload && (
        <label>
          {busy ? "Uploading…" : "Add photo or PDF (max 10 MB)"}
          <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={upload} disabled={busy} />
        </label>
      )}
      <ErrorMsg error={error} />
    </div>
  );
}

/** Sentinel-2 NDVI before vs after the practice, fetched on demand (it can take a few seconds). */
export function NdviPanel({ logId }) {
  const [state, setState] = useState({ started: false, loading: false, data: null, error: null });
  const run = async () => {
    setState({ started: true, loading: true, data: null, error: null });
    try {
      setState({ started: true, loading: false, data: await api.ndvi(logId), error: null });
    } catch (error) {
      setState({ started: true, loading: false, data: null, error });
    }
  };
  const cell = (s) => (s ? `${s.mean_ndvi ?? "n/a"} (${s.scene_date}, ${Math.round(s.cloud_cover ?? 0)}% cloud)` : "no clear scene");

  return (
    <div>
      <strong>Satellite check (NDVI)</strong>
      {!state.started && <p><button className="ghost" onClick={run}>Run Sentinel-2 check</button></p>}
      {state.loading && <p className="muted">Querying satellite archive…</p>}
      <ErrorMsg error={state.error} />
      {state.data && (
        <ul>
          <li>Before: {cell(state.data.before)}</li>
          <li>After: {cell(state.data.after)}</li>
          <li>
            Change: <b>{state.data.delta == null ? "not available" : (state.data.delta > 0 ? "+" : "") + state.data.delta}</b>
          </li>
          <li className="muted">A verification signal only: partly cloudy scenes and seasonality affect NDVI.</li>
        </ul>
      )}
    </div>
  );
}
