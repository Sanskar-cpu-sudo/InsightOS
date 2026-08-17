function HeroPanel({ loading, onRunPipeline, onRefresh }) {
  return (
    <section className="hero-panel">
      <div>
        <p className="eyebrow">Decision Command Center</p>
        <h2>Understand what changed, why it happened, and what to do next.</h2>
        <p>
          Monitor revenue signals, review AI recommendations, ask business questions,
          and keep decision outcomes in one clean workspace.
        </p>
      </div>

      <div className="hero-actions">
        <button className="primary-button" onClick={onRunPipeline} disabled={loading}>
          {loading ? "Running..." : "Run Pipeline"}
        </button>
        <button className="secondary-button" onClick={onRefresh} disabled={loading}>
          Refresh
        </button>
      </div>
    </section>
  );
}

export default HeroPanel;
