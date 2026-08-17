import { formatPercent } from "../utils/format";

function DecisionCard({ decision, onOutcome, loading, featured, delay = 0 }) {
  return (
    <article className={featured ? "decision-card featured-card" : "decision-card"} style={{ animationDelay: `${delay * 60}ms` }}>
      <div className="decision-top">
        <div>
          <span className="confidence-pill">{formatPercent(decision.confidence)} confidence</span>
          <h3>{decision.root_cause || "Decision"}</h3>
        </div>
        {decision.outcome && <span className="outcome-pill">{decision.outcome}</span>}
      </div>

      <p>{decision.recommendation}</p>

      <div className="score-row">
        <span>Faithfulness {formatPercent(decision.faithfulness_score)}</span>
        <span>Relevance {formatPercent(decision.relevance_score)}</span>
      </div>

      {decision.evidence?.length > 0 && (
        <div className="evidence-box">
          {decision.evidence.slice(0, 3).map((item, index) => (
            <span key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</span>
          ))}
        </div>
      )}

      {onOutcome && (
        <div className="outcome-actions">
          <button disabled={loading} onClick={() => onOutcome(decision.id, "resolved")}>
            Resolved
          </button>
          <button disabled={loading} onClick={() => onOutcome(decision.id, "false_positive")}>
            False Positive
          </button>
          <button disabled={loading} onClick={() => onOutcome(decision.id, "ignored")}>
            Ignored
          </button>
        </div>
      )}
    </article>
  );
}

export default DecisionCard;
