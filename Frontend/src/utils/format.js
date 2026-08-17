export function formatPercent(value) {
  if (value === null || value === undefined) {
    return "N/A";
  }

  return `${Math.round(Number(value) * 100)}%`;
}

export function formatMoney(value) {
  return `$${Number(value || 0).toLocaleString()}`;
}

export function prettifyKey(key) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
