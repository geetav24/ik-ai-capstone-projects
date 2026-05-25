import { useEffect, useState } from "react";
import { fetchLoans, fetchLoan } from "../../api/reviewApi";

const SCENARIO_QUESTIONS = {
  "LN-001": "Is this application ready to approve?",
  "LN-002": "Applicant is missing income documents — what do we need before proceeding?",
  "LN-003": "Self-employed borrower with high loan-to-income ratio. Should we approve?",
  "LN-004": "All risk factors are elevated. What is your recommendation?",
  "LN-005": "Applicant has zero income. Can this loan proceed?",
  "LN-006": "Review this application and flag any concerns.",
};

const EMPTY_FORM = {
  loan_id: "", borrower_name: "", loan_type: "personal",
  loan_amount: "", annual_income: "", credit_score: "",
  employment_status: "employed", submitted_documents: [], question: "",
};

export default function LoanReviewForm({ onSubmit, loading }) {
  const [loans, setLoans] = useState([]);
  const [form, setForm]   = useState(EMPTY_FORM);

  useEffect(() => {
    fetchLoans().then(setLoans).catch((err) => console.error("fetchLoans:", err));
  }, []);

  async function handleScenarioSelect(e) {
    const loanId = e.target.value;
    if (!loanId) { setForm(EMPTY_FORM); return; }
    try {
      const loan = await fetchLoan(loanId);
      setForm({ ...loan, question: SCENARIO_QUESTIONS[loanId] || "" });
    } catch { /* keep current form */ }
  }

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    const { question, ...applicationFields } = form;
    onSubmit({
      application: {
        ...applicationFields,
        loan_amount:   Number(form.loan_amount),
        annual_income: Number(form.annual_income),
        credit_score:  Number(form.credit_score),
      },
      question,
    });
  }

  return (
    <form className="card form-card" onSubmit={handleSubmit}>
      <h2>Loan Review Request</h2>
      <label>
        Load Demo Scenario
        <select onChange={handleScenarioSelect} defaultValue="">
          <option value="">— select a loan —</option>
          {loans.map((l) => (
            <option key={l.loan_id} value={l.loan_id}>
              {l.loan_id} · {l.borrower_name} · {l.loan_type} · ${Number(l.loan_amount).toLocaleString()}
            </option>
          ))}
        </select>
      </label>
      <hr />
      <div className="grid two">
        <label>Loan ID<input name="loan_id" value={form.loan_id} onChange={handleChange} required /></label>
        <label>Borrower Name<input name="borrower_name" value={form.borrower_name} onChange={handleChange} required /></label>
        <label>
          Loan Type
          <select name="loan_type" value={form.loan_type} onChange={handleChange}>
            <option value="personal">Personal</option>
            <option value="mortgage">Mortgage</option>
            <option value="auto">Auto</option>
            <option value="business">Business</option>
          </select>
        </label>
        <label>
          Employment Status
          <select name="employment_status" value={form.employment_status} onChange={handleChange}>
            <option value="employed">Employed</option>
            <option value="self_employed">Self Employed</option>
            <option value="unemployed">Unemployed</option>
            <option value="retired">Retired</option>
          </select>
        </label>
        <label>Loan Amount<input name="loan_amount" type="number" value={form.loan_amount} onChange={handleChange} required /></label>
        <label>Annual Income<input name="annual_income" type="number" value={form.annual_income} onChange={handleChange} required /></label>
        <label>Credit Score<input name="credit_score" type="number" value={form.credit_score} onChange={handleChange} required /></label>
        <label>
          Submitted Documents
          <input value={form.submitted_documents.map((d) => d.doc_type).join(", ") || "none"} readOnly style={{ color: "#888" }} />
        </label>
      </div>
      <label>
        Reviewer Question
        <textarea name="question" value={form.question} onChange={handleChange} rows="3" required />
      </label>
      <button disabled={loading} type="submit">
        {loading && <span className="spinner" />}
        {loading ? "Running Agents…" : "Review Loan"}
      </button>
    </form>
  );
}
