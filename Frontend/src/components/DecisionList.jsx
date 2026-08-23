import DecisionCard from "./DecisionCard";
import EmptyState from "./EmptyState";

export default function DecisionList({ decisions, onSetOutcome, busyId }) {
  if (!decisions || decisions.length === 0) {
    return <EmptyState title="No decisions yet" body="Once the pipeline runs, investigated incidents will show up here." />;
  }

  return (
    <div className="decision-list">
      {decisions.map((decision, i) => (
        <DecisionCard
          key={decision.id}
          decision={decision}
          onSetOutcome={onSetOutcome}
          busy={busyId === decision.id}
          index={i}
        />
      ))}
    </div>
  );
}
