export default function Metric({ label, value, tone, context, mutedContext, index = 0, children }) {
  const toneClass = tone ? `is-${tone}` : "";

  return (
    <div className="metric-card" style={{ animationDelay: `${index * 0.05}s` }}>
      <div>
        <div className="metric-card__label">{label}</div>
        <div className={`metric-card__value ${toneClass}`}>{value}</div>
      </div>
      {children ? (
        children
      ) : context ? (
        <div className={`metric-card__context ${mutedContext ? "is-muted" : ""}`}>{context}</div>
      ) : null}
    </div>
  );
}
