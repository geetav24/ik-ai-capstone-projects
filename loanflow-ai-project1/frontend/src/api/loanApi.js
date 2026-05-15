const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function _get(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

export function fetchLoans() {
  return _get("/loans");
}

export function fetchLoan(loanId) {
  return _get(`/loans/${loanId}`);
}

export async function reviewLoan({ application, question }) {
  const res = await fetch(`${API_BASE}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ application, question }),
  });
  if (!res.ok) throw new Error(`Review failed: ${res.status}`);
  return res.json();
}
