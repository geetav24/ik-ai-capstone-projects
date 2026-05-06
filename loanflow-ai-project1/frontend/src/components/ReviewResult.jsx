export default function ReviewResult({ result }) {
  if (!result) {
    return (
      <section className="card">
        <h2>Result</h2>
        <p>Submit a loan review request to run the LangGraph workflow.</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>AI Review Result</h2>
      <p>{result.answer}</p>

      <h3>Review Decision</h3>
      <p>
        <b>Status:</b>{" "}
        {result.requiresHumanReview ? "Human Review Required" : "No Human Review Required"}
      </p>

      <h3>Loan Metrics</h3>
      <ul>
        <li><b>Credit Score:</b> {result.credit_score}</li>
        <li><b>Loan Amount:</b> ${result.loan_amount}</li>
        <li><b>Annual Income:</b> ${result.annual_income}</li>
      </ul>

      <h3>Missing Documents</h3>
      <ul>
        {result.missingDocuments?.map((doc, index) => (
          <li key={index}>{doc}</li>
        ))}
      </ul>

      <h3>Risk Flags</h3>
      <ul>
        {result.riskFlags?.map((flag, index) => (
          <li key={index}>{flag}</li>
        ))}
      </ul>

      <h3>Guardrails Applied</h3>
      <ul>
        {result.guardrailsApplied?.map((guardrail, index) => (
          <li key={index}>{guardrail}</li>
        ))}
      </ul>

      <h3>Agent Trace</h3>
      <ol>
        {result.agentTrace?.map((step, index) => (
          <li key={index}>{step}</li>
        ))}
      </ol>

      {result.evaluation && (
        <>
          <h3>Evaluation</h3>
          <p><b>Decision Quality:</b> {result.evaluation.decision_quality}</p>
          <p><b>Reasoning:</b> {result.evaluation.reasoning}</p>
          <p><b>Hallucination Risk:</b> {result.evaluation.hallucination_risk}</p>
          <p><b>Policy Compliance:</b> {result.evaluation.policy_compliance}</p>
        </>
      )}
    </section>
  );
}