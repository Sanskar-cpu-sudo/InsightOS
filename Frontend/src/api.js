const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function handle(response) {
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = body.reason || body.detail || "";
    } catch {
      /* response wasn't JSON -- fall through with no extra detail */
    }
    throw new Error(detail ? `Request failed: ${detail}` : `Request failed (${response.status})`);
  }
  return response.json();
}

export function fetchDashboard() {
  return fetch(`${API_BASE_URL}/dashboard`).then(handle);
}

export function fetchHistory() {
  return fetch(`${API_BASE_URL}/history`).then(handle);
}

export function fetchWeeklyReport(days = 7) {
  return fetch(`${API_BASE_URL}/reports/weekly?days=${days}`).then(handle);
}

export function runPipelineNow() {
  return fetch(`${API_BASE_URL}/recommendations/run-now`, { method: "POST" }).then(handle);
}

export function askQuestion(question) {
  const params = new URLSearchParams({ question });
  return fetch(`${API_BASE_URL}/recommendations/ask?${params.toString()}`, { method: "POST" }).then(handle);
}

export function setDecisionOutcome(decisionId, outcome) {
  const params = new URLSearchParams({ outcome });
  return fetch(`${API_BASE_URL}/history/${decisionId}/outcome?${params.toString()}`, {
    method: "POST",
  }).then(handle);
}

export function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);
  return fetch(`${API_BASE_URL}/upload`, { method: "POST", body: formData }).then(handle);
}
