function ListBlock({ title, items }) {
  return (
    <div className="mini-card">
      <h3>{title}</h3>
      {items?.length ? (
        <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
      ) : (
        <p className="muted">None detected</p>
      )}
    </div>
  );
}

export default function ReviewResult({ result }) {
  if (!result) {
    return (
      <section className="card empty-state">
        <h2>Result</h2>
        <p>Submit a loan review request to run the LangGraph workflow.</p>
      </section>
    );
  }

  return (
    <section className="card result-card">
      <div className="result-header">
        <div>
          <p className="eyebrow">AI Review Result</p>
          <h2>{result.loan_id} — {result.borrower_name}</h2>
        </div>
        <span className="status-pill">Human Review: {result.requires_human_review ? "Required" : "Not Required"}</span>
      </div>

      <div className="answer-box">{result.answer}</div>

      <div className="grid three">
        <ListBlock title="Missing Documents" items={result.missing_documents} />
        <ListBlock title="Risk Flags" items={result.risk_flags} />
        <ListBlock title="Guardrails" items={result.guardrails_applied} />
      </div>

      <div className="mini-card">
        <h3>Agent Trace</h3>
        <ol>
          {result.agent_trace?.map((step, idx) => (
            <li key={`${step.agent}-${idx}`}><strong>{step.agent}:</strong> {step.summary}</li>
          ))}
        </ol>
      </div>

      {result.evaluation && (
        <div className="evaluation">
          <h3>Evaluation Score: {result.evaluation.score}/100</h3>
          <p>{result.evaluation.feedback?.join(" ")}</p>
        </div>
      )}
    </section>
  );
}