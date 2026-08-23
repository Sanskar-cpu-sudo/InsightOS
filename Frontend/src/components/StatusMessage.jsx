/**
 * StatusMessage -- loading / error / success banner used across pages.
 * tone: "loading" | "error" | "success" | "info"
 */
export default function StatusMessage({ tone = "info", title, body, action }) {
  const toneClass = tone === "error" ? "is-error" : tone === "success" ? "is-success" : "";

  return (
    <div className={`status-message ${toneClass}`}>
      {tone === "loading" && <div className="spinner" role="status" aria-label="Loading" />}
      <div className="status-message__title">{title}</div>
      {body && <div className="status-message__body">{body}</div>}
      {action}
    </div>
  );
}
