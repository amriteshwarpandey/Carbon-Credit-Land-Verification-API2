import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import Farmers from "./pages/Farmers";
import FarmerDetail from "./pages/FarmerDetail";
import PlotDetail from "./pages/PlotDetail";
import ReviewQueue from "./pages/ReviewQueue";
import Users from "./pages/Users";
import Account from "./pages/Account";

const ROLE_LABEL = { admin: "Admin", field_agent: "Field agent", auditor: "Auditor" };

function Shell({ children }) {
  const { user, logout } = useAuth();
  const link = ({ isActive }) => (isActive ? "active" : undefined);
  return (
    <>
      <header className="topbar">
        <strong className="brand">Carbon Console</strong>
        <nav>
          <NavLink to="/farmers" className={link}>Farmers</NavLink>
          {(user.role === "auditor" || user.role === "admin") && (
            <NavLink to="/review" className={link}>Review queue</NavLink>
          )}
          {user.role === "admin" && <NavLink to="/users" className={link}>Users</NavLink>}
        </nav>
        <span className="spacer" />
        <NavLink to="/account" className={link}>
          {user.full_name || user.email} · {ROLE_LABEL[user.role]}
        </NavLink>
        <button className="ghost" onClick={logout}>Sign out</button>
      </header>
      <main>{children}</main>
    </>
  );
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <p className="center muted">Loading…</p>;
  if (!user) return <Login />;

  const canReview = user.role === "auditor" || user.role === "admin";
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Navigate to={user.role === "auditor" ? "/review" : "/farmers"} replace />} />
        <Route path="/farmers" element={<Farmers />} />
        <Route path="/farmers/:id" element={<FarmerDetail />} />
        <Route path="/plots/:id" element={<PlotDetail />} />
        <Route path="/review" element={canReview ? <ReviewQueue /> : <Navigate to="/" replace />} />
        <Route path="/users" element={user.role === "admin" ? <Users /> : <Navigate to="/" replace />} />
        <Route path="/account" element={<Account />} />
        <Route path="*" element={<p className="muted">Page not found.</p>} />
      </Routes>
    </Shell>
  );
}
