function Metric({ title, value, detail, tone }) {
  return (
    <article className={`metric metric-${tone}`}>
      <span>{title}</span>
      <strong>{value ?? "N/A"}</strong>
      <small>{detail}</small>
    </article>
  );
}

export default Metric;
