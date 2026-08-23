export default function PanelTitle({ eyebrow, heading, sub }) {
  return (
    <div className="panel-title">
      {eyebrow && <div className="panel-title__eyebrow">{eyebrow}</div>}
      <div className="panel-title__heading">{heading}</div>
      {sub && <div className="panel-title__sub">{sub}</div>}
    </div>
  );
}
