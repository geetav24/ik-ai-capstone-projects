import { useRef, useState, useEffect } from "react";
import ChatMessage from "./ChatMessage.jsx";
import { sendMessage, clearSession } from "../../api/chatApi.js";

function makeSessionId() {
  return crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}`;
}

export default function ChatWindow() {
  const [messages, setMessages]   = useState([]);   // {role, content, meta}
  const [input, setInput]         = useState("");
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");
  const [memoryType, setMemoryType] = useState("buffer");
  const [sessionId]               = useState(makeSessionId);

  const bottomRef = useRef(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const data = await sendMessage({ sessionId, message: text, memoryType });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer || "(no answer)",
          meta: {
            injection_signals: data.injection_signals || [],
            redactions:        data.redactions || [],
            agent_trace:       data.agent_trace || [],
            intent:            data.intent,
          },
        },
      ]);
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    // Send on Enter (not Shift+Enter)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleClear() {
    try { await clearSession(sessionId); } catch { /* ignore */ }
    setMessages([]);
    setError("");
  }

  return (
    <div className="chat-layout">
      {/* Toolbar */}
      <div className="chat-toolbar">
        <label>
          Memory:
          <select value={memoryType} onChange={(e) => setMemoryType(e.target.value)}>
            <option value="buffer">Buffer (last 10 turns)</option>
            <option value="summary">Summary (compressed)</option>
          </select>
        </label>
        <button onClick={handleClear}>Clear chat</button>
        <span style={{ marginLeft: "auto", opacity: 0.5 }}>
          session: {sessionId.slice(0, 8)}…
        </span>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Message list */}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Ask about loan policy, check a status (e.g. LN-004),</p>
            <p>or find out how much you can borrow.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <ChatMessage key={i} role={m.role} content={m.content} meta={m.meta} />
        ))}
        {loading && (
          <div className="msg assistant">
            <div className="msg-bubble" style={{ opacity: 0.6 }}>
              <span className="spinner" style={{ borderColor: "#aaa", borderTopColor: "transparent" }} />
              {" "}thinking…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
          disabled={loading}
        />
        <button onClick={handleSend} disabled={loading || !input.trim()}>
          {loading ? <span className="spinner" /> : "Send"}
        </button>
      </div>
    </div>
  );
}
