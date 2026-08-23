import RevenueBar from "./RevenueBar";

export default function HeroPanel({ points, openAlerts }) {
  const hasOpenAlerts = openAlerts > 0;

  return (
    <section className="hero-panel">
      <div className="hero-panel__header">
        <div className="hero-panel__title">Revenue Vitals</div>
        <div className="hero-panel__meta">{points?.length || 0}-day trace</div>
      </div>

      <div className="status-line" style={{ marginBottom: "1rem" }}>
        <span>
          <span className={`status-dot ${hasOpenAlerts ? "is-alert" : "is-nominal"}`} />
          {hasOpenAlerts ? `${openAlerts} OPEN ALERT${openAlerts === 1 ? "" : "S"}` : "SYSTEM NOMINAL"}
        </span>
      </div>

      <RevenueBar points={points} hasOpenAlerts={hasOpenAlerts} />
    </section>
  );
}
