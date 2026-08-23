import { useCallback, useEffect, useState } from "react";
import { fetchDashboard, fetchWeeklyReport, runPipelineNow } from "../api";
import HeroPanel from "../components/HeroPanel";
import Metric from "../components/Metric";
import PanelTitle from "../components/PanelTitle";
import StatusMessage from "../components/StatusMessage";
import WeeklyReport from "../components/WeeklyReport";
import { formatDecimal, formatPercent, toneHigherIsBetter, toneLowerIsBetter } from "../utils/format";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [report, setReport] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [errorMessage, setErrorMessage] = useState("");
  const [runStatus, setRunStatus] = useState(null); // null | "running" | { success, reason }

  const load = useCallback(() => {
    setStatus("loading");
    Promise.all([fetchDashboard(), fetchWeeklyReport(7)])
      .then(([dashboardData, reportData]) => {
        setData(dashboardData);
        setReport(reportData);
        setStatus("ready");
      })
      .catch((err) => {
        setErrorMessage(err.message || "Something went wrong.");
        setStatus("error");
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleRunNow = async () => {
    setRunStatus("running");
    try {
      const result = await runPipelineNow();
      setRunStatus(result);
      load();
    } catch (err) {
      setRunStatus({ success: false, reason: err.message });
    }
  };

  const openAlerts = data?.open_alerts ?? 0;

  return (
    <div className="page-content">
      <div className="hero-panel__header" style={{ marginBottom: "0" }}>
        <PanelTitle eyebrow="Operations" heading="Dashboard" />
        <button type="button" className="btn btn-primary" onClick={handleRunNow} disabled={runStatus === "running"}>
          {runStatus === "running" ? "Running…" : "Run Pipeline Now"}
        </button>
      </div>

      {runStatus && runStatus !== "running" && (
        <div style={{ marginBottom: "1.25rem" }}>
          <StatusMessage
            tone={runStatus.success ? "success" : "error"}
            title={runStatus.success ? "Pipeline run complete" : "Pipeline run skipped or failed"}
            body={runStatus.success ? "A new decision was recorded below." : runStatus.reason}
          />
        </div>
      )}

      {status === "loading" && <StatusMessage tone="loading" title="Reading vitals…" body="Pulling the latest figures from the backend." />}

      {status === "error" && (
        <StatusMessage
          tone="error"
          title="Couldn't reach the dashboard"
          body={errorMessage}
          action={
            <button type="button" className="btn btn-primary" style={{ marginTop: "1rem" }} onClick={load}>
              Retry
            </button>
          }
        />
      )}

      {status === "ready" && data && (
        <>
          <HeroPanel points={data.revenue_trend} openAlerts={openAlerts} />

          <PanelTitle eyebrow="Evaluation" heading="System Readings" />
          <div className="metric-grid" style={{ marginBottom: "1.75rem" }}>
            <Metric
              index={0}
              label="Open Alerts"
              value={openAlerts}
              tone={openAlerts > 0 ? "alert" : "nominal"}
              context={openAlerts > 0 ? "Awaiting review" : "Nothing outstanding"}
            />
            <Metric
              index={1}
              label="Avg. Confidence"
              value={formatDecimal(data.average_confidence)}
              tone={toneHigherIsBetter(data.average_confidence)}
              context={`Last ${data.decisions_evaluated ?? 0} decisions`}
            />
            <Metric
              index={2}
              label="Avg. Faithfulness"
              value={formatDecimal(data.average_faithfulness)}
              tone={toneHigherIsBetter(data.average_faithfulness)}
              context="Grounded in evidence"
            />
            <Metric
              index={3}
              label="Avg. Relevance"
              value={formatDecimal(data.average_relevance)}
              tone={toneHigherIsBetter(data.average_relevance)}
              context="Matches the question"
            />
            <Metric
              index={4}
              label="Resolution Rate"
              value={formatPercent(data.resolution_rate)}
              tone={toneHigherIsBetter(data.resolution_rate)}
              context="Of reviewed decisions"
            />
            <Metric
              index={5}
              label="False Positive Rate"
              value={formatPercent(data.false_positive_rate)}
              tone={toneLowerIsBetter(data.false_positive_rate)}
              context="Of reviewed decisions"
            />
            <Metric
              index={6}
              label="Decisions Reviewed"
              value={data.decisions_reviewed ?? "—"}
              context="Of last 100 decisions"
            />
            <Metric index={7} label="Cost & Latency" value="—">
              <div className="metric-card__context is-muted">{data.note || "Not yet instrumented."}</div>
            </Metric>
          </div>

          <WeeklyReport report={report} />
        </>
      )}
    </div>
  );
}
