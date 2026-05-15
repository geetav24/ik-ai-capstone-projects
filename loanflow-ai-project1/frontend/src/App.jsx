import { useState } from "react";
import DemoHeader from "./components/DemoHeader.jsx";
import LoanReviewForm from "./components/LoanReviewForm.jsx";
import ReviewResult from "./components/ReviewResult.jsx";
import { reviewLoan } from "./api/loanApi.js";

export default function App() {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleReview(payload) {
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const data = await reviewLoan(payload);
      setResult(data);
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <DemoHeader />
      {error && <div className="error-banner">{error}</div>}
      <div className="layout">
        <LoanReviewForm onSubmit={handleReview} loading={loading} />
        <ReviewResult result={result} />
      </div>
    </main>
  );
}