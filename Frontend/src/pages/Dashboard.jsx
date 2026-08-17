import DecisionList from "../components/DecisionList";
import EmptyState from "../components/EmptyState";
import Metric from "../components/Metric";
import PanelTitle from "../components/PanelTitle";
import RevenueBar from "../components/RevenueBar";
import WeeklyReport from "../components/WeeklyReport";
import { formatPercent } from "../utils/format";

function Dashboard({ dashboard, recommendations, report }) {
  if (!dashboard) {
    return <EmptyState text="No dashboard data yet." />;
  }

  return (
    <>
      <div className="metric-grid">
        <Metric title="Open Alerts" value={dashboard.open_alerts} detail="Unresolved decisions" tone="pink" />
        <Metric title="Confidence" value={formatPercent(dashboard.average_confidence)} detail="Average model certainty" tone="green" />
        <Metric title="Faithfulness" value={formatPercent(dashboard.average_faithfulness)} detail="Evidence alignment" tone="blue" />
        <Metric title="Resolution" value={formatPercent(dashboard.resolution_rate)} detail="Reviewed success rate" tone="amber" />
      </div>

      <div className="split-grid">
        <section className="panel large-panel">
          <PanelTitle eyebrow="Last 7 days" title="Revenue Trend" />
          {dashboard.revenue_trend?.length ? (
            <div className="chart-list">
              {dashboard.revenue_trend.map((item) => (
                <RevenueBar key={item.date} item={item} items={dashboard.revenue_trend} />
              ))}
            </div>
          ) : (
            <EmptyState text="No recent sales data found." />
          )}
        </section>

        <section className="panel">
          <PanelTitle eyebrow="Generated Summary" title="Weekly Report" />
          <WeeklyReport report={report} />
        </section>
      </div>

      <section className="panel">
        <PanelTitle eyebrow="AI Suggestions" title="Latest Recommendations" />
        <DecisionList decisions={recommendations} />
      </section>
    </>
  );
}

export default Dashboard;
