import DecisionCard from "../components/DecisionCard";
import EmptyState from "../components/EmptyState";
import PanelTitle from "../components/PanelTitle";

function AskPage({ question, setQuestion, answer, handleAsk, loading }) {
  return (
    <div className="split-grid ask-grid">
      <section className="panel prompt-panel">
        <PanelTitle eyebrow="On Demand" title="Ask InsightOS" />
        <form onSubmit={handleAsk} className="form-stack">
          <label htmlFor="question">Question</label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Example: Why did revenue drop this week?"
          />
          <button className="primary-button" disabled={loading}>
            Ask Question
          </button>
        </form>
      </section>

      <section className="panel answer-panel">
        <PanelTitle eyebrow="Response" title="Answer" />
        {answer ? <DecisionCard decision={answer} featured /> : <EmptyState text="Your answer will appear here." />}
      </section>
    </div>
  );
}

export default AskPage;
