import DecisionCard from "./DecisionCard";
import EmptyState from "./EmptyState";

function DecisionList({ decisions, onOutcome, loading }) {
  if (!decisions?.length) {
    return <EmptyState text="No decisions found." />;
  }

  return (
    <div className="decision-list">
      {decisions.map((decision, index) => (
        <DecisionCard
          key={decision.id || decision.recommendation}
          decision={decision}
          onOutcome={onOutcome}
          loading={loading}
          delay={index}
        />
      ))}
    </div>
  );
}

export default DecisionList;
