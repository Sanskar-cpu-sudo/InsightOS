import { useCallback, useEffect, useState } from "react";
import { fetchHistory, setDecisionOutcome } from "../api";
import DecisionList from "../components/DecisionList";
import PanelTitle from "../components/PanelTitle";
import StatusMessage from "../components/StatusMessage";

export default function HistoryPage() {
  const [decisions, setDecisions] = useState(null);
  const [status, setStatus] = useState("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    setStatus("loading");
    fetchHistory()
      .then((data) => {
        setDecisions(data.history || []);
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

  const handleSetOutcome = async (decisionId, outcome) => {
    setBusyId(decisionId);
    try {
      await setDecisionOutcome(decisionId, outcome);
      setDecisions((prev) => prev.map((d) => (d.id === decisionId ? { ...d, outcome } : d)));
    } catch (err) {
      setErrorMessage(err.message || "Couldn't update that decision.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="page-content">
      <PanelTitle eyebrow="Decision Memory" heading="History" sub="Every decision the system has made, and whether it turned out to be right." />

      {status === "loading" && <StatusMessage tone="loading" title="Loading history…" />}

      {status === "error" && (
        <StatusMessage
          tone="error"
          title="Couldn't load history"
          body={errorMessage}
          action={
            <button type="button" className="btn btn-primary" style={{ marginTop: "1rem" }} onClick={load}>
              Retry
            </button>
          }
        />
      )}

      {status === "ready" && <DecisionList decisions={decisions} onSetOutcome={handleSetOutcome} busyId={busyId} />}
    </div>
  );
}
