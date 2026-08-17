function PanelTitle({ eyebrow, title }) {
  return (
    <div className="panel-title">
      <span>{eyebrow}</span>
      <h2>{title}</h2>
    </div>
  );
}

export default PanelTitle;
