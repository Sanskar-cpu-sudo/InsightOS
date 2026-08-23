import { formatDecimal, formatPercent } from "../utils/format";
import EmptyState from "./EmptyState";
import PanelTitle from "./PanelTitle";

export default function WeeklyReport({ report }) {
  if (!report) return null;

  const { total_decisions, incidents_detected, resolution_rate, recurring_patterns, average_confidence, outcome_breakdown } = report;

  return (
    <section>
      <PanelTitle eyebrow={`Last ${report.period_days} days`} heading="Weekly Report" />

      <div className="weekly-report">
        {total_decisions === 0 ? (
          <EmptyState
            title="Nothing to report yet"
            body="No decisions were made in this window. Run the pipeline or wait for the scheduler."
          />
        ) : (
          <>
            <div className="weekly-report__stats">
              <div>
                <div className="weekly-report__stat-label">Total Decisions</div>
                <div className="weekly-report__stat-value">{total_decisions}</div>
              </div>
              <div>
                <div className="weekly-report__stat-label">Incidents Detected</div>
                <div className="weekly-report__stat-value">{incidents_detected}</div>
              </div>
              <div>
                <div className="weekly-report__stat-label">Resolution Rate</div>
                <div className="weekly-report__stat-value">{formatPercent(resolution_rate)}</div>
              </div>
            </div>

            {recurring_patterns && recurring_patterns.length > 0 && (
              <div style={{ marginBottom: "1rem" }}>
                <div className="weekly-report__stat-label" style={{ marginBottom: "0.5rem" }}>
                  Recurring Patterns
                </div>
                <div className="pattern-list">
                  {recurring_patterns.map((p) => (
                    <span className="pattern-chip" key={p.metric}>
                      <strong>{p.metric}</strong> × {p.occurrences}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="pattern-list">
              <span className="pattern-chip">
                Avg. confidence <strong>{formatDecimal(average_confidence)}</strong>
              </span>
              {outcome_breakdown && (
                <>
                  <span className="pattern-chip">
                    Resolved <strong>{outcome_breakdown.resolved}</strong>
                  </span>
                  <span className="pattern-chip">
                    False positive <strong>{outcome_breakdown.false_positive}</strong>
                  </span>
                  <span className="pattern-chip">
                    Still open <strong>{outcome_breakdown.still_open}</strong>
                  </span>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
