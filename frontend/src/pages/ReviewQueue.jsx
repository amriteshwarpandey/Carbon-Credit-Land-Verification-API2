import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../hooks";
import { EvidencePanel, NdviPanel } from "../components/LogDetails";
import { ErrorMsg, Loading, PRACTICE_LABEL, StatusBadge } from "../components/ui";

function Row({ item, canReview, onDone }) {
  const [notes, setNotes] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);

  const act = async (kind) => {
    setBusy(true);
    setError(null);
    try {
      await api[kind](item.id, notes);
      onDone();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <>
    <tr>
      <td>{item.id}</td>
      <td><Link to={`/plots/${item.plot_id}`}>Plot #{item.plot_id}</Link></td>
      <td>{PRACTICE_LABEL[item.practice]}{item.quantity ? ` (${item.quantity})` : ""}</td>
      <td>{item.performed_on}</td>
      <td className="wrap">{item.notes || "—"}</td>
      <td>
        <button className="ghost" onClick={() => setShow(!show)}>
          {show ? "Hide" : `Evidence (${item.evidence_count})`}
        </button>
      </td>
      <td>
        {item.status === "pending" ? (
          canReview ? (
            <div className="review">
              <input placeholder="Review notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} />
              <button disabled={busy} onClick={() => act("approve")}>Approve</button>
              <button className="danger" disabled={busy} onClick={() => act("reject")}>Reject</button>
              <ErrorMsg error={error} />
            </div>
          ) : <span className="muted">Auditor action needed</span>
        ) : (
          <><StatusBadge status={item.status} /> {item.co2e_tonnes != null && `${item.co2e_tonnes} tCO₂e`}</>
        )}
      </td>
    </tr>
    {show && (
      <tr>
        <td colSpan="7">
          <EvidencePanel logId={item.id} canUpload={false} />
          <NdviPanel logId={item.id} />
        </td>
      </tr>
    )}
    </>
  );
}

const TABS = ["pending", "approved", "rejected"];

export default function ReviewQueue() {
  const { user } = useAuth();
  const [tab, setTab] = useState("pending");
  const items = useAsync(() => api.interventions(tab), [tab]);

  return (
    <>
      <h2>Review queue</h2>
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t} className={t === tab ? "active" : "ghost"} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {user.role === "admin" && <p className="muted">Only auditors can approve or reject.</p>}
      <Loading state={items} />
      {items.data && (
        <table>
          <thead><tr><th>ID</th><th>Plot</th><th>Practice</th><th>Performed</th><th>Agent notes</th><th>Evidence</th><th>Decision</th></tr></thead>
          <tbody>
            {items.data.map((i) => (
              <Row key={i.id} item={i} canReview={user.role === "auditor"} onDone={items.reload} />
            ))}
            {!items.data.length && <tr><td colSpan="7" className="muted">Nothing {tab}.</td></tr>}
          </tbody>
        </table>
      )}
    </>
  );
}
