export function ErrorMsg({ error }) {
  return error ? <p className="error" role="alert">{error.message || String(error)}</p> : null;
}

export function StatusBadge({ status }) {
  return <span className={`badge ${status}`}>{status}</span>;
}

export function Loading({ state }) {
  if (state.loading) return <p className="muted">Loading…</p>;
  if (state.error) return <ErrorMsg error={state.error} />;
  return null;
}

export const fmtDate = (s) => (s ? new Date(s).toLocaleString() : "—");
export const PRACTICE_LABEL = {
  no_till: "No-till",
  cover_crop: "Cover crop",
  biochar: "Biochar",
  tree_planting: "Tree planting",
};
export const PRACTICE_UNIT = { biochar: "tonnes of biochar", tree_planting: "number of trees" };
