import { useEffect, useState } from "react";
import {
  askQuestion,
  getDashboard,
  getHistory,
  getRecommendations,
  getWeeklyReport,
  runPipelineNow,
  updateDecisionOutcome,
  uploadPdf,
} from "./api";
import AppFooter from "./components/AppFooter";
import AppHeader from "./components/AppHeader";
import HeroPanel from "./components/HeroPanel";
import StatusMessage from "./components/StatusMessage";
import AskPage from "./pages/AskPage";
import Dashboard from "./pages/Dashboard";
import HistoryPage from "./pages/HistoryPage";
import UploadPage from "./pages/UploadPage";

function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [dashboard, setDashboard] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [history, setHistory] = useState([]);
  const [report, setReport] = useState(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [file, setFile] = useState(null);
  const [messages, setMessages] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadAllData();
  }, []);

  useEffect(() => {
    clearMessage(activeTab);
  }, [activeTab]);

  function showMessage(tab, text, type = "info") {
    setMessages((oldMessages) => ({
      ...oldMessages,
      [tab]: { text, type },
    }));

    window.setTimeout(() => clearMessage(tab), 3500);
  }

  function clearMessage(tab) {
    setMessages((oldMessages) => {
      if (!oldMessages[tab]) {
        return oldMessages;
      }

      const updatedMessages = { ...oldMessages };
      delete updatedMessages[tab];
      return updatedMessages;
    });
  }

  async function loadAllData() {
    setLoading(true);

    try {
      const [dashboardData, recommendationData, historyData, reportData] =
        await Promise.all([
          getDashboard(),
          getRecommendations(),
          getHistory(),
          getWeeklyReport(7),
        ]);

      setDashboard(dashboardData);
      setRecommendations(recommendationData.recommendations || []);
      setHistory(historyData.history || []);
      setReport(reportData);
    } catch (error) {
      showMessage(activeTab, `Could not load data: ${error.message}`, "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleAsk(event) {
    event.preventDefault();

    if (!question.trim()) {
      showMessage("ask", "Please enter a question.", "warning");
      return;
    }

    setLoading(true);

    try {
      const result = await askQuestion(question);
      setAnswer(result.decision);
      setQuestion("");
      await loadAllData();
      showMessage("ask", "Answer generated successfully.", "success");
    } catch (error) {
      showMessage("ask", `Question failed: ${error.message}`, "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunPipeline() {
    setLoading(true);

    try {
      const result = await runPipelineNow();
      await loadAllData();
      showMessage(
        activeTab,
        result.success ? "Pipeline finished successfully." : `Pipeline stopped: ${result.reason}`,
        result.success ? "success" : "warning"
      );
    } catch (error) {
      showMessage(activeTab, `Pipeline failed: ${error.message}`, "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(event) {
    event.preventDefault();

    if (!file) {
      showMessage("upload", "Please choose a PDF file.", "warning");
      return;
    }

    setLoading(true);

    try {
      const result = await uploadPdf(file);
      setFile(null);
      event.target.reset();
      showMessage("upload", `Uploaded ${result.filename}. Stored ${result.chunks_stored} chunks.`, "success");
    } catch (error) {
      showMessage("upload", `Upload failed: ${error.message}`, "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleOutcome(id, outcome) {
    setLoading(true);

    try {
      await updateDecisionOutcome(id, outcome);
      await loadAllData();
      showMessage("history", "Outcome updated.", "success");
    } catch (error) {
      showMessage("history", `Update failed: ${error.message}`, "error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <div className="page-glow page-glow-one" />
      <div className="page-glow page-glow-two" />

      <AppHeader activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="main-layout">
        <HeroPanel loading={loading} onRunPipeline={handleRunPipeline} onRefresh={loadAllData} />
        <StatusMessage message={messages[activeTab]} />
        {loading && <div className="loading-line"><span /> Syncing with backend</div>}

        <section className="content-stage" key={activeTab}>
          {activeTab === "dashboard" && (
            <Dashboard dashboard={dashboard} recommendations={recommendations} report={report} />
          )}

          {activeTab === "ask" && (
            <AskPage
              question={question}
              setQuestion={setQuestion}
              answer={answer}
              handleAsk={handleAsk}
              loading={loading}
            />
          )}

          {activeTab === "history" && (
            <HistoryPage decisions={history} onOutcome={handleOutcome} loading={loading} />
          )}

          {activeTab === "upload" && (
            <UploadPage file={file} setFile={setFile} handleUpload={handleUpload} loading={loading} />
          )}
        </section>
      </main>

      <AppFooter />
    </div>
  );
}

export default App;
