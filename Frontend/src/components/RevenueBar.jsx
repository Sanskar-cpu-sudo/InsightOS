import { formatMoney } from "../utils/format";

function RevenueBar({ item, items }) {
  const maxRevenue = Math.max(...items.map((row) => Number(row.revenue || 0)), 1);
  const width = Math.max((Number(item.revenue) / maxRevenue) * 100, 8);

  return (
    <div className="chart-row">
      <span>{item.date}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${width}%` }} />
      </div>
      <strong>{formatMoney(item.revenue)}</strong>
    </div>
  );
}

export default RevenueBar;
