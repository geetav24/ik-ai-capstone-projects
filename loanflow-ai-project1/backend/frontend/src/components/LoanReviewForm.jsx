import { useState } from "react";

const sample = {
  loan_id: "LN-1001",
  borrower_name: "Jane Smith",
  loan_amount: 250000,
  annual_income: 95000,
  credit_score: 680,
  question: "Borrower is missing bank statements. What should reviewer check?",
};

export default function LoanReviewForm({ onSubmit, loading }) {
  const [form, setForm] = useState(sample);

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function handleSubmit(event) {
    event.preventDefault();

    // Convert numeric inputs before sending to FastAPI/Pydantic.
    onSubmit({
      ...form,
      loan_amount: Number(form.loan_amount),
      annual_income: Number(form.annual_income),
      credit_score: Number(form.credit_score),
    });
  }

  return (
    <form className="card form-card" onSubmit={handleSubmit}>
      <h2>Loan Review Request</h2>
      <div className="grid two">
        <label>
          Loan ID
          <input name="loan_id" value={form.loan_id} onChange={handleChange} />
        </label>
        <label>
          Borrower Name
          <input name="borrower_name" value={form.borrower_name} onChange={handleChange} />
        </label>
        <label>
          Loan Amount
          <input name="loan_amount" type="number" value={form.loan_amount} onChange={handleChange} />
        </label>
        <label>
          Annual Income
          <input name="annual_income" type="number" value={form.annual_income} onChange={handleChange} />
        </label>
        <label>
          Credit Score
          <input name="credit_score" type="number" value={form.credit_score} onChange={handleChange} />
        </label>
      </div>
      <label>
        Reviewer Question
        <textarea name="question" value={form.question} onChange={handleChange} rows="4" />
      </label>
      <button disabled={loading} type="submit">
        {loading ? "Running Agents..." : "Review Loan"}
      </button>
    </form>
  );
}