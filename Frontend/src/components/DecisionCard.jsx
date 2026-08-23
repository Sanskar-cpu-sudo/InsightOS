import { formatDateTime, formatDecimal, outcomeLabel, outcomeTone } from "../utils/format";

/**
 * DecisionCard -- one decision, shown in HistoryPage's list or as the
 * result of an Ask question.
 *
 * onSetOutcome (optional): if provided, renders action buttons to mark
 * the decision resolved / false positive / ignored. Omitted entirely
 * on already-reviewed decisions or where the caller doesn't want
 * review actions (e.g. a fresh Ask result).
 */
export default function DecisionCard({ decision, onSetOutcome, busy, index = 0 }) {
  const {
    id,
    created_at,
    root_cause,
    recommendation,
    confidence,
    faithfulness_score,
    relevance_score,
    outcome,
  } = decision;

  return (
    <div className="decision-card" style={{ animationDelay: `${index * 0.04}s` }}>
      <div className="decision-card__top">
        <div className="decision-card__date">{created_at ? formatDateTime(created_at) : "Just now"}</div>
        <span className={`badge ${outcomeTone(outcome) ? `is-${outcomeTone(outcome)}` : ""}`}>
          {outcomeLabel(outcome)}
        </span>
      </div>

      <div className="decision-card__root-cause">{root_cause}</div>
      <div className="decision-card__recommendation">{recommendation}</div>

      <div className="decision-card__footer">
        <div className="decision-card__scores">
          <span>CONF {formatDecimal(confidence)}</span>
          {faithfulness_score !== undefined && <span>FAITH {formatDecimal(faithfulness_score)}</span>}
          {relevance_score !== undefined && <span>RELEV {formatDecimal(relevance_score)}</span>}
        </div>

        {onSetOutcome && !outcome && (
          <div className="decision-card__actions">
            <button
              type="button"
              className="btn btn-outline btn-sm"
              disabled={busy}
              onClick={() => onSetOutcome(id, "resolved")}
            >
              Resolved
            </button>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              disabled={busy}
              onClick={() => onSetOutcome(id, "false_positive")}
            >
              False positive
            </button>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              disabled={busy}
              onClick={() => onSetOutcome(id, "ignored")}
            >
              Ignore
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
