import { useState } from "react";
import { askQuestion } from "../api";
import DecisionCard from "../components/DecisionCard";
import PanelTitle from "../components/PanelTitle";
import StatusMessage from "../components/StatusMessage";

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | success | blocked | error
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    setStatus("loading");
    setResult(null);

    try {
      const response = await askQuestion(question.trim());
      if (response.success) {
        setResult(response.decision);
        setStatus("success");
      } else {
        setErrorMessage(response.reason || "The question was blocked.");
        setStatus("blocked");
      }
    } catch (err) {
      setErrorMessage(err.message || "Something went wrong.");
      setStatus("error");
    }
  };

  return (
    <div className="page-content">
      <PanelTitle
        eyebrow="On-demand"
        heading="Ask InsightOS"
        sub="Ask a question about your business data — the same pipeline that investigates anomalies automatically will search for evidence and reason through an answer."
      />

      <form className="form-panel" onSubmit={handleSubmit}>
        <textarea
          className="ask-textarea"
          placeholder="e.g. why did revenue drop recently?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={status === "loading"}
        />
        <div className="form-panel__actions">
          <button type="submit" className="btn btn-primary" disabled={status === "loading" || !question.trim()}>
            {status === "loading" ? "Investigating…" : "Ask"}
          </button>
        </div>
      </form>

      {status === "loading" && (
        <StatusMessage tone="loading" title="Searching for evidence…" body="Running retrieval and reasoning over your business data." />
      )}

      {status === "blocked" && <StatusMessage tone="error" title="Question was blocked" body={errorMessage} />}

      {status === "error" && <StatusMessage tone="error" title="Something went wrong" body={errorMessage} />}

      {status === "success" && result && (
        <>
          <PanelTitle eyebrow="Result" heading="Answer" />
          <div className="decision-list">
            <DecisionCard decision={result} />
          </div>
        </>
      )}
    </div>
  );
}
