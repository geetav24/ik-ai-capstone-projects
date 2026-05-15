import { useState } from "react";
import ReactMarkdown from "react-markdown";

const SEVERITY_COLOR = {
  low:      "#2e7d32",
  medium:   "#f57c00",
  high:     "#c62828",
  critical: "#7b1fa2",
};

function GroundingBar({ score }) {
  const pct   = Math.round((score ?? 0) * 100);
  const color = pct >= 70 ? "#2e7d32" : pct >= 40 ? "#f57c00" : "#c62828";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{ flex: 1, background: "#eee", borderRadius: 4, height: 10 }}>
        <div style={{ width: `${pct}%`, background: color, borderRadius: 4, height: "100%", transition: "width 0.4s" }} />
      </div>
      <span style={{ minWidth: 40, fontWeight: 600, color }}>{pct}%</span>
    </div>
  );
}

function Collapsible({ title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginTop: "1rem" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          background: "none", border: "none", cursor: "pointer",
          fontWeight: 700, fontSize: "1em", padding: 0,
          display: "flex", alignItems: "center", gap: 6, color: "#333",
        }}
      >
        <span style={{ fontSize: "0.75em" }}>{open ? "▼" : "▶"}</span>
        {title}
      </button>
      {open && <div style={{ marginTop: 8 }}>{children}</div>}
    </div>
  );
}

export default function ReviewResult({ result }) {
  if (!result) {
    return (
      <section className="card">
        <h2>Result</h2>
        <p>Submit a loan review request to run the agent pipeline.</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>AI Review Result</h2>

      {/* Decision badge */}
      <div style={{ marginBottom: "1rem" }}>
        <span style={{
          display: "inline-block", padding: "6px 14px", borderRadius: 4,
          background: result.requires_human_review ? "#fff3e0" : "#e8f5e9",
          color:      result.requires_human_review ? "#e65100" : "#2e7d32",
          fontWeight: 700, fontSize: "1em",
        }}>
          {result.requires_human_review ? "⚠ Human Review Required" : "✓ No Human Review Required"}
        </span>
      </div>

      {/* Answer — rendered markdown */}
      <div style={{ lineHeight: 1.7 }}>
        <ReactMarkdown>{result.answer}</ReactMarkdown>
      </div>

      {/* Missing documents */}
      {result.missing_documents?.length > 0 && (
        <Collapsible title="Missing Documents" defaultOpen>
          <ul>
            {result.missing_documents.map((doc) => (
              <li key={doc} style={{ color: "#c62828" }}>{doc}</li>
            ))}
          </ul>
        </Collapsible>
      )}

      {/* Risk flags */}
      {result.risk_flags?.length > 0 && (
        <Collapsible title="Risk Flags" defaultOpen>
          <ul>
            {result.risk_flags.map((flag, i) => (
              <li key={i}>
                <span style={{ color: SEVERITY_COLOR[flag.severity] || "#333", fontWeight: 600 }}>
                  [{flag.severity?.toUpperCase()}]
                </span>{" "}
                <b>{flag.flag_type}</b> — {flag.detail}
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {/* Fraud findings */}
      {result.fraud_findings?.signals?.length > 0 && (
        <Collapsible title="Fraud Signals" defaultOpen>
          <p>Confidence: <b>{(result.fraud_findings.confidence * 100).toFixed(0)}%</b></p>
          <ul>
            {result.fraud_findings.signals.map((s) => (
              <li key={s} style={{ color: "#c62828" }}>{s}</li>
            ))}
          </ul>
        </Collapsible>
      )}

      {/* Injection signals */}
      {result.injection_signals?.length > 0 && (
        <Collapsible title="⚠ Injection Signals Detected" defaultOpen>
          <ul>
            {result.injection_signals.map((s) => (
              <li key={s} style={{ color: "#7b1fa2" }}>{s}</li>
            ))}
          </ul>
        </Collapsible>
      )}

      {/* Policy citations */}
      {result.citations?.length > 0 && (
        <Collapsible title={`Policy Citations (${result.citations.length})`} defaultOpen>
          {result.citations.map((c, i) => (
            <div key={i} style={{ background: "#f5f5f5", padding: "8px 12px", marginBottom: 8, borderRadius: 4 }}>
              <small style={{ color: "#666" }}>
                {c.filename} · chunk {c.chunk_index} · score {c.score?.toFixed(3)}
              </small>
              <p style={{ margin: "4px 0 0", fontSize: "0.9em" }}>{c.text}</p>
            </div>
          ))}
        </Collapsible>
      )}

      {/* Evaluation */}
      {result.evaluation && (
        <Collapsible title="LLM-as-Judge Evaluation" defaultOpen>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9em" }}>
            <tbody>
              <tr style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "6px 8px", fontWeight: 600, width: "40%" }}>Decision Quality</td>
                <td style={{ padding: "6px 8px" }}>{result.evaluation.decision_quality}</td>
              </tr>
              <tr style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "6px 8px", fontWeight: 600 }}>Grounding Score</td>
                <td style={{ padding: "6px 8px", minWidth: 160 }}>
                  <GroundingBar score={result.evaluation.grounding_score} />
                </td>
              </tr>
              <tr style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "6px 8px", fontWeight: 600 }}>Hallucination Risk</td>
                <td style={{ padding: "6px 8px" }}>{result.evaluation.hallucination_risk}</td>
              </tr>
              <tr style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "6px 8px", fontWeight: 600 }}>Policy Compliance</td>
                <td style={{ padding: "6px 8px" }}>{result.evaluation.policy_compliance}</td>
              </tr>
            </tbody>
          </table>
          <p style={{ marginTop: 8, fontSize: "0.9em" }}><b>Reasoning:</b> {result.evaluation.reasoning}</p>
        </Collapsible>
      )}

      {/* Guardrails applied */}
      {result.guardrails_applied?.length > 0 && (
        <Collapsible title="Guardrails Applied">
          <ul>
            {result.guardrails_applied.map((g) => <li key={g}>{g}</li>)}
          </ul>
        </Collapsible>
      )}

      {/* Agent trace — collapsed by default */}
      {result.agent_trace?.length > 0 && (
        <Collapsible title={`Agent Trace (${result.agent_trace.length} steps)`} defaultOpen={false}>
          <ol style={{ fontSize: "0.85em", paddingLeft: "1.2rem" }}>
            {result.agent_trace.map((step, i) => (
              <li key={i} style={{ marginBottom: 8 }}>
                <b>{step.agent}</b> — {step.output_summary}
                <br />
                <small style={{ color: "#888" }}>{step.input_summary}</small>
              </li>
            ))}
          </ol>
        </Collapsible>
      )}
    </section>
  );
}
