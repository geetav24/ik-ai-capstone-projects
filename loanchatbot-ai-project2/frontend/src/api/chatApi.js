// Calls Project 2 backend (LoanInquiry AI) — port 8002
const BASE = import.meta.env.VITE_CHAT_API_BASE_URL || "http://127.0.0.1:8002";

export async function sendMessage({ sessionId, message, memoryType = "buffer" }) {
  const res = await fetch(`${BASE}/v2/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      memory_type: memoryType,
    }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
  return res.json();
}

export async function clearSession(sessionId) {
  const res = await fetch(`${BASE}/chat/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Clear session failed: ${res.status}`);
  return res.json();
}
