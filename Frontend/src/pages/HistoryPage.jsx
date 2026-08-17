import DecisionList from "../components/DecisionList";
import PanelTitle from "../components/PanelTitle";

function HistoryPage({ decisions, onOutcome, loading }) {
  return (
    <section className="panel">
      <PanelTitle eyebrow="Decision Memory" title="History" />
      <DecisionList decisions={decisions} onOutcome={onOutcome} loading={loading} />
    </section>
  );
}

export default HistoryPage;
