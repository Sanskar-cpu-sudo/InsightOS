import { formatShortDate } from "../utils/format";
import EmptyState from "./EmptyState";

/**
 * RevenueBar -- animated bar-chart rendering of the revenue trend.
 * Each bar grows in from zero on mount (staggered), and the most
 * recent bar is colored by whether there are currently open alerts --
 * the one piece of real status data we have to attach to it, rather
 * than guessing which historical day was anomalous.
 */
export default function RevenueBar({ points, hasOpenAlerts }) {
  if (!points || points.length === 0) {
    return <EmptyState title="No revenue data yet" body="Once sales data is seeded, the trend will chart here." />;
  }

  const values = points.map((p) => p.revenue);
  const maxV = Math.max(...values);
  const minV = Math.min(0, Math.min(...values));
  const range = maxV - minV || 1;

  return (
    <div className="revenue-bar-chart" role="img" aria-label="Revenue trend bar chart">
      {points.map((p, i) => {
        const heightPct = ((p.revenue - minV) / range) * 100;
        const isLast = i === points.length - 1;
        return (
          <div className="revenue-bar-chart__col" key={p.date}>
            <div className="revenue-bar-chart__track">
              <div
                className={`revenue-bar-chart__bar ${isLast && hasOpenAlerts ? "is-alert" : ""}`}
                style={{ height: `${heightPct}%`, animationDelay: `${i * 0.04}s` }}
                title={`${formatShortDate(p.date)}: ${p.revenue.toLocaleString()}`}
              />
            </div>
            <div className="revenue-bar-chart__label">{formatShortDate(p.date)}</div>
          </div>
        );
      })}
    </div>
  );
}
