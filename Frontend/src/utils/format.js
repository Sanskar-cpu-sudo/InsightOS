export function formatDecimal(value, places = 2) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(places);
}

export function formatPercent(value) {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

export function formatShortDate(dateStr) {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatDateTime(dateStr) {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// higher-is-better tiering (confidence, faithfulness, relevance, resolution rate)
export function toneHigherIsBetter(value) {
  if (value === null || value === undefined) return undefined;
  if (value >= 0.7) return "nominal";
  if (value >= 0.4) return "caution";
  return "alert";
}

// lower-is-better tiering (false positive rate)
export function toneLowerIsBetter(value) {
  if (value === null || value === undefined) return undefined;
  if (value <= 0.2) return "nominal";
  if (value <= 0.5) return "caution";
  return "alert";
}

export function outcomeLabel(outcome) {
  if (!outcome) return "Open";
  if (outcome === "false_positive") return "False positive";
  return outcome.charAt(0).toUpperCase() + outcome.slice(1);
}

export function outcomeTone(outcome) {
  if (!outcome) return "caution";
  if (outcome === "resolved") return "nominal";
  if (outcome === "false_positive") return "alert";
  return undefined; // "ignored" -- neutral
}
