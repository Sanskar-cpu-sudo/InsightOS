import StatusMessage from "./StatusMessage";

export default function EmptyState({ title, body }) {
  return <StatusMessage tone="info" title={title} body={body} />;
}
