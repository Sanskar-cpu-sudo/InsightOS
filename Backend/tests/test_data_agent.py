"""
tests/test_data_agent.py

Anomaly detection + the correlation logic that bundles multiple
metrics moving together into one incident, instead of reporting
several unrelated-looking alerts for what's actually one problem.
"""

import random
from datetime import date, timedelta

from app.models import Sale
from app.agents.data_agent import run_data_agent


def _seed_stable_history(db, days=13, seed=7):
    """13 days of noisy-but-stable sales, ending yesterday."""
    random.seed(seed)
    today = date.today()
    for i in range(days, 0, -1):
        rev = 10000.0 + random.uniform(-300, 300)
        orders = 200 + random.randint(-8, 8)
        db.add(Sale(company_id=1, date=today - timedelta(days=i), revenue=rev, orders=orders, avg_order_value=round(rev / orders, 2)))
    db.commit()


def test_no_anomaly_on_stable_data(db):
    """A normal day should not produce any false positives."""
    _seed_stable_history(db)
    today = date.today()
    db.add(Sale(company_id=1, date=today, revenue=10050.0, orders=201, avg_order_value=50.0))
    db.commit()

    result = run_data_agent(db, company_id=1)

    assert result["anomalies_found"] == 0
    assert result["correlation"]["is_correlated"] is False
    assert result["incident"] is None


def test_correlated_drop_is_bundled_into_one_incident(db):
    """
    Real scenario: revenue AND orders crash together on the same day.
    Must be detected as ONE correlated incident, not two disconnected
    alerts -- this is the whole point of Phase 3.
    """
    _seed_stable_history(db)
    today = date.today()
    db.add(Sale(company_id=1, date=today, revenue=4000.0, orders=80, avg_order_value=50.0))
    db.commit()

    result = run_data_agent(db, company_id=1)

    assert result["anomalies_found"] >= 2
    assert result["correlation"]["is_correlated"] is True
    assert "revenue" in result["correlation"]["metrics_involved"]
    assert "orders" in result["correlation"]["metrics_involved"]

    assert result["incident"] is not None
    assert result["incident"]["severity"] == "high"
    assert set(result["incident"]["metrics"]) == {"revenue", "orders"}


def test_single_metric_anomaly_is_not_treated_as_an_incident(db):
    """
    revenue alone declining, with orders/AOV staying in the normal
    noise band, should NOT be bundled into an incident -- correlation
    requires two or more metrics genuinely moving together.
    """
    random.seed(3)
    today = date.today()
    for i in range(13, 0, -1):
        frac = (13 - i) / 13
        rev = 10000.0 - 3000 * frac + random.uniform(-100, 100)
        orders = 200 + random.randint(-5, 5)
        db.add(Sale(company_id=1, date=today - timedelta(days=i), revenue=rev, orders=orders, avg_order_value=50.0))
    db.add(Sale(company_id=1, date=today, revenue=6500.0, orders=201, avg_order_value=50.0))
    db.commit()

    result = run_data_agent(db, company_id=1)

    assert result["correlation"]["is_correlated"] is False
    assert result["incident"] is None


def test_same_metric_reported_twice_does_not_count_as_correlated(db):
    """
    A point_anomaly and a trend_anomaly on the SAME metric (revenue)
    is still just one thing acting up, not a multi-metric incident.
    """
    from app.agents.data_agent import find_same_window_correlation

    result = find_same_window_correlation([
        {"metric": "revenue", "type": "point_anomaly"},
        {"metric": "revenue", "type": "trend_anomaly"},
    ])

    assert result["is_correlated"] is False
    assert result["metrics_involved"] == ["revenue"]
