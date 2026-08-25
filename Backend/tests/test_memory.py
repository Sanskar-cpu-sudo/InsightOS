"""
tests/test_memory.py

The exact bug class this guards against: incident-shaped topics (which
store metrics under "metrics", plural) used to silently collide under
a generic "unknown" key in duplicate detection, since the code only
ever checked topic.get("metric") (singular). That meant a genuinely
NEW, different incident could get wrongly treated as a duplicate of an
unrelated one -- or worse, the metric shown in saved evidence was
always wrong for every incident-based decision.
"""

from app.memory import _extract_metric_key, save_decision, is_duplicate_recent_decision


def test_extract_metric_key_for_single_anomaly():
    assert _extract_metric_key({"type": "point_anomaly", "metric": "revenue"}) == "revenue"


def test_extract_metric_key_for_incident_is_stable_regardless_of_order():
    key_a = _extract_metric_key({"incident": "x", "metrics": ["revenue", "orders"]})
    key_b = _extract_metric_key({"incident": "x", "metrics": ["orders", "revenue"]})

    assert key_a == key_b == "orders+revenue"


def test_extract_metric_key_for_user_question():
    assert _extract_metric_key({"type": "user_question", "question": "why?"}) == "unknown"


def test_save_decision_rejects_true_duplicate(db):
    incident = {"incident": "checkout_performance", "metrics": ["orders", "revenue"], "severity": "high", "anomalies": []}
    decision_result = {"root_cause": "x", "recommendation": "y", "confidence": 0.9, "evidence_used": ["a"]}
    scores = {"faithfulness_score": 0.8, "relevance_score": 0.7}

    first = save_decision(db, 1, incident, decision_result, scores)
    second = save_decision(db, 1, incident, decision_result, scores)

    assert first is not None
    assert second is None  # correctly rejected as a duplicate


def test_save_decision_does_not_confuse_different_incidents(db):
    """
    The exact bug: two DIFFERENT incidents used to both collapse to the
    same 'unknown' key and could wrongly dedupe against each other.
    """
    decision_result = {"root_cause": "x", "recommendation": "y", "confidence": 0.9, "evidence_used": ["a"]}
    scores = {"faithfulness_score": 0.8, "relevance_score": 0.7}

    incident_a = {"incident": "checkout_performance", "metrics": ["orders", "revenue"], "severity": "high", "anomalies": []}
    incident_b = {"incident": "pricing_or_cart_value", "metrics": ["avg_order_value", "revenue"], "severity": "high", "anomalies": []}

    saved_a = save_decision(db, 1, incident_a, decision_result, scores)
    saved_b = save_decision(db, 1, incident_b, decision_result, scores)

    assert saved_a is not None
    assert saved_b is not None  # must NOT be treated as a duplicate of incident_a


def test_save_decision_stores_correct_metric_key_for_incident(db):
    incident = {"incident": "checkout_performance", "metrics": ["orders", "revenue"], "severity": "high", "anomalies": []}
    decision_result = {"root_cause": "x", "recommendation": "y", "confidence": 0.9, "evidence_used": ["a"]}
    scores = {"faithfulness_score": 0.8, "relevance_score": 0.7}

    saved = save_decision(db, 1, incident, decision_result, scores)

    assert saved.evidence["metric"] == "orders+revenue"  # not "unknown"
