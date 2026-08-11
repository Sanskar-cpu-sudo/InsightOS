
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sklearn.ensemble import IsolationForest
import numpy as np

from app.models import Sale
from app.config import get_settings

settings = get_settings()


def get_recent_sales(db: Session, company_id: int = 1, days: int = None):
    """
    Gets the last N days of sales from the database.
    Returns a list of Sale rows, sorted by date.
    """
    if days is None:
        days = settings.ANOMALY_LOOKBACK_DAYS

    start_date = date.today() - timedelta(days=days)

    sales = (
        db.query(Sale)
        .filter(Sale.company_id == company_id)
        .filter(Sale.date >= start_date)
        .order_by(Sale.date)
        .all()
    )
    return sales


def find_point_anomaly(sales):
    """
    Checks if TODAY looks very different compared to the other days.
    We use Isolation Forest, a simple ML model that is good at finding
    the "odd one out" in a group of numbers.

    Returns a dict describing the anomaly, or None if today looks normal.
    """
    if len(sales) < 5:
        # not enough data to compare against
        return None

    # today is the last row (list is sorted by date)
    today_row = sales[-1]
    history_rows = sales[:-1]  # everything except today

    # Build a table of numbers: revenue, orders, avg_order_value
    history_data = []
    for row in history_rows:
        history_data.append([row.revenue, row.orders, row.avg_order_value])

    today_data = [[today_row.revenue, today_row.orders, today_row.avg_order_value]]

    # Train the model on history only (today is NOT included in training,
    # so today can't drag down its own baseline)
    model = IsolationForest(contamination=0.1, random_state=42)
    model.fit(history_data)

    # score_samples: higher score = more normal, lower score = more unusual
    today_score = model.score_samples(today_data)[0]
    history_scores = model.score_samples(history_data)

    average_history_score = np.mean(history_scores)

    # if today's score is a lot lower than the average history score,
    # today is unusual
    is_anomaly = today_score < (average_history_score - 0.15)

    if not is_anomaly:
        return None

    # figure out roughly how much revenue changed vs the average
    avg_revenue = np.mean([row.revenue for row in history_rows])
    percent_change = ((today_row.revenue - avg_revenue) / avg_revenue) * 100

    return {
        "type": "point_anomaly",
        "metric": "revenue",
        "date": str(today_row.date),
        "today_value": today_row.revenue,
        "normal_average": round(avg_revenue, 2),
        "percent_change": round(percent_change, 1),
        "severity": "high" if abs(percent_change) > 25 else "medium",
    }


def find_trend_anomaly(sales):
    """
    Checks if revenue has been steadily going DOWN over the whole window,
    even if no single day looked shocking. This catches the case where
    the "normal baseline" itself has slowly become bad.

    We fit a straight line through the revenue numbers and look at its
    slope (is the line going down, and by how much).
    """
    if len(sales) < 7:
        return None

    revenue_values = [row.revenue for row in sales]
    day_numbers = list(range(len(revenue_values)))  # 0, 1, 2, 3, ...

    # np.polyfit fits a straight line: revenue = slope * day + intercept
    slope, intercept = np.polyfit(day_numbers, revenue_values, 1)

    first_value = revenue_values[0]
    last_value = revenue_values[-1]
    total_percent_change = ((last_value - first_value) / first_value) * 100

    # only flag it if the decline is big enough to matter
    is_declining_trend = slope < 0 and total_percent_change < -15

    if not is_declining_trend:
        return None

    return {
        "type": "trend_anomaly",
        "metric": "revenue",
        "trend": "declining",
        "slope_per_day": round(slope, 2),
        "total_percent_change": round(total_percent_change, 1),
        "days_checked": len(sales),
        "severity": "high" if total_percent_change < -25 else "medium",
    }


def run_data_agent(db: Session, company_id: int = 1):
    """
    Main function other code calls to use the Data Agent.
    Runs both checks and returns everything it found.
    """
    sales = get_recent_sales(db, company_id=company_id)

    point_anomaly = find_point_anomaly(sales)
    trend_anomaly = find_trend_anomaly(sales)

    anomalies = []
    if point_anomaly:
        anomalies.append(point_anomaly)
    if trend_anomaly:
        anomalies.append(trend_anomaly)

    return {
        "agent": "data_agent",
        "days_analyzed": len(sales),
        "anomalies_found": len(anomalies),
        "anomalies": anomalies,
    }