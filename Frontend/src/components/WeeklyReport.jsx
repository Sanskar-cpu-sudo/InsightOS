import EmptyState from "./EmptyState";
import { prettifyKey } from "../utils/format";

function WeeklyReport({ report }) {
  if (!report) {
    return <EmptyState text="No report generated yet." />;
  }

  const summary = findText(report, ["summary", "weekly_summary", "executive_summary", "report"]);
  const recommendations = findList(report, ["recommendations", "recommended_actions", "actions", "next_steps"]);
  const themes = findList(report, ["themes", "top_themes", "recurring_issues", "incidents"]);
  const metrics = Object.entries(report).filter(([, value]) => typeof value === "number" || typeof value === "boolean");
  const details = Object.entries(report).filter(([, value]) => {
    return typeof value === "string" && value !== summary;
  });

  return (
    <div className="weekly-report">
      {summary && (
        <section className="report-summary">
          <span>Executive Summary</span>
          <p>{summary}</p>
        </section>
      )}

      {metrics.length > 0 && (
        <div className="report-metrics">
          {metrics.slice(0, 4).map(([key, value]) => (
            <article key={key}>
              <span>{prettifyKey(key)}</span>
              <strong>{String(value)}</strong>
            </article>
          ))}
        </div>
      )}

      <ReportList title="Key Themes" items={themes} />
      <ReportList title="Recommended Actions" items={recommendations} numbered />

      {details.length > 0 && (
        <div className="report-details">
          {details.slice(0, 5).map(([key, value]) => (
            <div key={key}>
              <strong>{prettifyKey(key)}</strong>
              <p>{value}</p>
            </div>
          ))}
        </div>
      )}

      {!summary && !recommendations.length && !themes.length && details.length === 0 && (
        <ReportFallback report={report} />
      )}
    </div>
  );
}

function ReportList({ title, items, numbered }) {
  if (!items.length) {
    return null;
  }

  const ListTag = numbered ? "ol" : "ul";

  return (
    <section className="report-list">
      <h3>{title}</h3>
      <ListTag>
        {items.slice(0, 6).map((item, index) => (
          <li key={index}>{formatItem(item)}</li>
        ))}
      </ListTag>
    </section>
  );
}

function ReportFallback({ report }) {
  return (
    <div className="report-details">
      {Object.entries(report).slice(0, 8).map(([key, value]) => (
        <div key={key}>
          <strong>{prettifyKey(key)}</strong>
          <p>{formatItem(value)}</p>
        </div>
      ))}
    </div>
  );
}

function findText(report, keys) {
  for (const key of keys) {
    if (typeof report[key] === "string" && report[key].trim()) {
      return report[key];
    }
  }

  return "";
}

function findList(report, keys) {
  for (const key of keys) {
    const value = report[key];

    if (Array.isArray(value)) {
      return value;
    }
  }

  return [];
}

function formatItem(item) {
  if (typeof item === "string") {
    return item;
  }

  if (item === null || item === undefined) {
    return "N/A";
  }

  if (typeof item === "object") {
    return Object.entries(item)
      .map(([key, value]) => `${prettifyKey(key)}: ${String(value)}`)
      .join(" | ");
  }

  return String(item);
}

export default WeeklyReport;
