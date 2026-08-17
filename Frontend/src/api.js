const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || data.reason || "Something went wrong");
  }

  return data;
}

export function getDashboard() {
  return request("/dashboard");
}

export function getRecommendations() {
  return request("/recommendations");
}

export function getHistory() {
  return request("/history");
}

export function getWeeklyReport(days) {
  return request(`/reports/weekly?days=${days}`);
}

export function runPipelineNow() {
  return request("/recommendations/run-now", { method: "POST" });
}

export function askQuestion(question) {
  const params = new URLSearchParams({ question });
  return request(`/recommendations/ask?${params.toString()}`, { method: "POST" });
}

export function updateDecisionOutcome(id, outcome) {
  const params = new URLSearchParams({ outcome });
  return request(`/history/${id}/outcome?${params.toString()}`, { method: "POST" });
}

export function uploadPdf(file) {
  const formData = new FormData();
  formData.append("file", file);

  return request("/upload", {
    method: "POST",
    body: formData,
  });
}
