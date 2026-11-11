const BASE = import.meta.env.VITE_API_URL || "/api";
const TOKEN_KEY = "carbon_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// FastAPI returns {detail: "msg"} or {detail: [{loc, msg}, ...]} for validation errors.
function detailToMessage(detail, fallback) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(1).join(".") || "input"}: ${d.msg}`).join("; ");
  }
  return fallback;
}

async function request(path, { method = "GET", body, form, formData, raw } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (formData) {
    payload = formData; // the browser sets the multipart boundary header itself
  } else if (form) {
    payload = new URLSearchParams(form);
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${path}`, { method, headers, body: payload });
  if (res.status === 401 && token) {
    setToken(null);
    window.dispatchEvent(new Event("auth-expired"));
  }
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detailToMessage(detail, `Request failed (${res.status})`));
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

export const api = {
  login: (email, password) => request("/auth/login", { method: "POST", form: { username: email, password } }),
  me: () => request("/auth/me"),
  createUser: (u) => request("/users", { method: "POST", body: u }),
  users: () => request("/users"),
  updateUser: (id, patch) => request(`/users/${id}`, { method: "PATCH", body: patch }),
  changePassword: (current_password, new_password) =>
    request("/auth/change-password", { method: "POST", body: { current_password, new_password } }),

  evidence: (logId) => request(`/interventions/${logId}/evidence`),
  uploadEvidence: (logId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/interventions/${logId}/evidence`, { method: "POST", formData: fd });
  },
  async openEvidence(logId, evidenceId) {
    const res = await request(`/interventions/${logId}/evidence/${evidenceId}`, { raw: true });
    const url = URL.createObjectURL(await res.blob());
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
  ndvi: (logId) => request(`/interventions/${logId}/ndvi`),

  farmers: () => request("/farmers"),
  farmer: (id) => request(`/farmers/${id}`),
  createFarmer: (f) => request("/farmers", { method: "POST", body: f }),
  ledger: (id) => request(`/farmers/${id}/ledger`),

  plots: (farmerId) => request(`/farmers/${farmerId}/plots`),
  plot: (id) => request(`/plots/${id}`),
  createPlot: (farmerId, p) => request(`/farmers/${farmerId}/plots`, { method: "POST", body: p }),
  weather: (id) => request(`/plots/${id}/weather`),

  plotInterventions: (plotId) => request(`/plots/${plotId}/interventions`),
  createIntervention: (plotId, i) => request(`/plots/${plotId}/interventions`, { method: "POST", body: i }),
  interventions: (status) => request(`/interventions${status ? `?status=${status}` : ""}`),
  approve: (id, notes) => request(`/interventions/${id}/approve`, { method: "POST", body: { notes: notes || null } }),
  reject: (id, notes) => request(`/interventions/${id}/reject`, { method: "POST", body: { notes: notes || null } }),

  // Certificates need the auth header, so fetch as a blob and open it rather than using a bare <a href>.
  async openCertificate(id, format = "pdf") {
    const res = await request(`/interventions/${id}/certificate?format=${format}`, { raw: true });
    const url = URL.createObjectURL(await res.blob());
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
};
