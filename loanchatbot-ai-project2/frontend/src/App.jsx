import { useState } from "react";
import LoanReviewForm from "./components/review/LoanReviewForm.jsx";
import ReviewResult from "./components/review/ReviewResult.jsx";
import ChatWindow from "./components/chat/ChatWindow.jsx";
import { reviewLoan } from "./api/reviewApi.js";

const TABS = [
  { id: "chat",   label: "💬 Loan Chat" },
  { id: "review", label: "🔍 Loan Review" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState("chat");

  // Review tab state
  const [reviewResult, setReviewResult] = useState(null);
  const [reviewError, setReviewError]   = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);

  async function handleReview(payload) {
    setReviewError("");
    setReviewResult(null);
    setReviewLoading(true);
    try {
      const data = await reviewLoan(payload);
      setReviewResult(data);
    } catch (err) {
      setReviewError(err.message || "Review request failed");
    } finally {
      setReviewLoading(false);
    }
  }

  return (
    <div className="app-shell">
      {/* Header */}
      <header className="app-header">
        <h1>LoanInquiry AI</h1>
        <span className="badge">Multi-Agent</span>
      </header>

      {/* Tab bar */}
      <nav className="tab-bar">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={activeTab === t.id ? "active" : ""}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Chat tab — Project 2 ADK pipeline */}
      {activeTab === "chat" && <ChatWindow />}

      {/* Review tab — Project 1 LangGraph pipeline */}
      {activeTab === "review" && (
        <>
          {reviewError && <div className="error-banner">{reviewError}</div>}
          <div className="layout">
            <LoanReviewForm onSubmit={handleReview} loading={reviewLoading} />
            <ReviewResult result={reviewResult} />
          </div>
        </>
      )}
    </div>
  );
}
