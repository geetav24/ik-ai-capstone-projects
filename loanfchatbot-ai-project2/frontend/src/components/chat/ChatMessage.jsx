import { useState } from "react";
import ReactMarkdown from "react-markdown";

export default function ChatMessage({ role, content, meta }) {
  const [showTrace, setShowTrace] = useState(false);

  const hasInjection = meta?.injection_signals?.length > 0;
  const hasRedactions = meta?.redactions?.length > 0;
  const hasTrace = meta?.agent_trace?.length > 0;

  return (
    <div className={`msg ${role}`}>
      <div className="msg-bubble">
        {role === "assistant"
          ? <ReactMarkdown>{content}</ReactMarkdown>
          : content}
      </div>

      {/* Pills — only on assistant messages with signals */}
      {role === "assistant" && (hasInjection || hasRedactions) && (
        <div className="msg-pills">
          {hasInjection && (
            <span className="pill pill-injection">⚠ injection blocked</span>
          )}
          {hasRedactions && (
            <span className="pill pill-redacted">
              PII redacted: {meta.redactions.join(", ")}
            </span>
          )}
        </div>
      )}

      {/* Agent trace toggle — only on assistant messages */}
      {role === "assistant" && hasTrace && (
        <>
          <span className="msg-trace" onClick={() => setShowTrace((s) => !s)}>
            {showTrace ? "▲ hide" : "▶ show"} agent trace ({meta.agent_trace.length} steps)
          </span>
          {showTrace && (
            <div className="trace-detail">
              <ol>
                {meta.agent_trace.map((step, i) => (
                  <li key={i}>
                    <b>{step.agent}</b> — {step.output_summary}
                    <br />
                    <small style={{ color: "#888" }}>{step.input_summary}</small>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      )}
    </div>
  );
}
