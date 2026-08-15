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


# V2, Step 3.1: metrics (besides revenue) that we now also check
# individually for same-day anomalies. revenue keeps using the original
# find_point_anomaly() above, untouched -- these are the new ones.
ADDITIONAL_METRICS_TO_CHECK = ["orders", "avg_order_value"]


def find_point_anomaly_for_metric(sales, metric_name: str):
    """
    V2, Step 3.1: same idea as find_point_anomaly() above ("is today the
    odd one out"), generalized to work on any single metric field on
    Sale (orders, avg_order_value, ...), not just revenue.

    find_point_anomaly() above is intentionally left untouched -- it's
    V1's original revenue check, and it works well because it trains
    IsolationForest on revenue+orders+avg_order_value TOGETHER (a joint,
    3-feature model). A single-feature IsolationForest on a small sample
    (our lookback window is often only a couple weeks) turns out to be
    unreliable in practice -- tested directly against this data, it
    missed even an obvious, extreme same-day outlier. So rather than
    reuse IsolationForest here, this uses a plain z-score check: how many
    standard deviations away from the historical mean is today, which is
    the standard, more dependable approach for a single variable on a
    small sample.
    """
    if len(sales) < 5:
        return None

    values = [getattr(row, metric_name) for row in sales]
    today_row = sales[-1]
    history_values = values[:-1]
    today_value = values[-1]

    avg_value = np.mean(history_values)
    std_value = np.std(history_values)

    if std_value == 0:
        # history never varies at all -- any change today is the anomaly
        is_anomaly = today_value != avg_value
        z_score = float("inf") if is_anomaly else 0.0
    else:
        z_score = (today_value - avg_value) / std_value
        # 2 standard deviations out is a common, reasonably strict
        # threshold for "this looks genuinely unusual" without being so
        # tight that ordinary day-to-day noise keeps triggering it
        is_anomaly = abs(z_score) > 2

    if not is_anomaly:
        return None

    if avg_value == 0:
        percent_change = 0.0
    else:
        percent_change = ((today_value - avg_value) / avg_value) * 100

    return {
        "type": "point_anomaly",
        "metric": metric_name,
        "date": str(today_row.date),
        "today_value": today_value,
        "normal_average": round(avg_value, 2),
        "percent_change": round(percent_change, 1),
        "severity": "high" if abs(percent_change) > 25 else "medium",
    }


def find_same_window_correlation(anomalies: list) -> dict:
    """
    V2, Step 3.1: checks whether the anomalies found are CORRELATED --
    i.e. whether more than one metric looks anomalous at the same time,
    rather than just one metric acting up on its own.

    Every check in this module runs against the same "today"/lookback
    window within a single run_data_agent() call, so any anomalies that
    show up together here are, by construction, already in the same
    window. This function's real job is just to look at how many
    DISTINCT metrics are represented among them, and say whether that's
    enough to call it a correlated incident (2 or more distinct metrics)
    versus just one metric acting up alone.

    This does NOT build the incident object itself -- that's Step 3.2.
    It just answers the "are these related, and which metrics" question
    that Step 3.2's bundling will need.
    """
    metrics_involved = sorted({a["metric"] for a in anomalies})

    return {
        "is_correlated": len(metrics_involved) >= 2,
        "metrics_involved": metrics_involved,
        "anomaly_count": len(anomalies),
    }


# V2, Step 3.2: business-friendly names for known combinations of
# correlated metrics. frozenset so the key order doesn't matter.
# Falls back to a generic, still-readable label built from the metric
# names themselves for any combination not listed here.
INCIDENT_LABELS = {
    frozenset(["revenue", "orders"]): "checkout_performance",
    frozenset(["revenue", "avg_order_value"]): "pricing_or_cart_value",
    frozenset(["orders", "avg_order_value"]): "order_volume_and_value",
    frozenset(["revenue", "orders", "avg_order_value"]): "checkout_performance",
}


def build_incident(anomalies: list, correlation: dict):
    """
    V2, Step 3.2: takes the individual anomalies + the correlation check
    from Step 3.1, and -- ONLY if they're actually correlated -- bundles
    them into a single incident object, e.g.:

        {"incident": "checkout_performance", "metrics": ["revenue", "orders"],
         "severity": "high", "anomalies": [...], "anomaly_count": 2}

    This is what lets the rest of the pipeline treat "revenue AND orders
    both crashed together" as ONE thing to investigate, instead of two
    separate, disconnected anomalies competing for attention.

    Returns None if correlation["is_correlated"] is False -- in that
    case there's nothing to bundle, callers should keep using the
    anomalies list exactly as they do today (see Step 3.4, which will
    make graph.py handle both shapes).
    """
    if not correlation["is_correlated"]:
        return None

    metrics_involved = correlation["metrics_involved"]
    label = INCIDENT_LABELS.get(
        frozenset(metrics_involved),
        "_and_".join(metrics_involved) + "_incident",
    )

    # the incident is as severe as its most severe individual anomaly
    overall_severity = "high" if any(a["severity"] == "high" for a in anomalies) else "medium"

    return {
        "incident": label,
        "metrics": metrics_involved,
        "severity": overall_severity,
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
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
    Runs both V1 checks (revenue point + trend), PLUS (V2, Step 3.1) a
    point-anomaly check on the other metrics, then checks whether
    everything found is happening in the same window (correlated).
    """
    sales = get_recent_sales(db, company_id=company_id)

    point_anomaly = find_point_anomaly(sales)
    trend_anomaly = find_trend_anomaly(sales)

    anomalies = []
    if point_anomaly:
        anomalies.append(point_anomaly)
    if trend_anomaly:
        anomalies.append(trend_anomaly)

    # V2, Step 3.1: also check the other metrics individually. Any of
    # these firing on the SAME run as the revenue check above means
    # they're already in the same window (see find_same_window_correlation).
    for metric_name in ADDITIONAL_METRICS_TO_CHECK:
        metric_anomaly = find_point_anomaly_for_metric(sales, metric_name)
        if metric_anomaly:
            anomalies.append(metric_anomaly)

    correlation = find_same_window_correlation(anomalies)
    incident = build_incident(anomalies, correlation)

    return {
        "agent": "data_agent",
        "days_analyzed": len(sales),
        "anomalies_found": len(anomalies),
        "anomalies": anomalies,
        "correlation": correlation,
        "incident": incident,
    }