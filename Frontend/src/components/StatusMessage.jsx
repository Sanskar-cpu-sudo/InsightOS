function StatusMessage({ message }) {
  if (!message) {
    return null;
  }

  return <div className={`status-message status-${message.type || "info"}`}>{message.text}</div>;
}

export default StatusMessage;
