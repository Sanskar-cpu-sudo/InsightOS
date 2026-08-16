"""
agents/report_agent.py

Phase 7, Step 7.1: the Report Agent.

Unlike the other agents, this one doesn't investigate a live anomaly --
it looks BACKWARD at what's already in Decision Memory over the last
few days, and summarizes it: what kept coming up, whether it's a
correlated incident or a one-off, and how much of it actually got
resolved versus ignored or turned out to be a false alarm.

This is purely data-driven (no LLM call) -- everything here is counting
and grouping decisions that already exist, not generating new analysis.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Decision

DEFAULT_REPORT_DAYS = 7


def _extract_metrics(decision: Decision) -> list:
    """
    Pulls the metric(s) a decision was actually about, straight from the
    "topic" dict stashed in decision.evidence at save time.

    NOTE: this deliberately does NOT use decision.evidence.get("metric")
    (also stored by save_decision() in memory.py) -- that field only
    ever gets set correctly for single-anomaly topics. For an INCIDENT
    topic (Phase 3.4), which stores its metrics under "metrics" (plural),
    that lookup silently falls back to "unknown" for every single one.
    Reading "topic" directly here and handling both shapes ourselves
    sidesteps that gap without needing to touch memory.py for this step.
    """
    evidence = decision.evidence or {}
    topic = evidence.get("topic", {}) or {}

    if topic.get("type") == "user_question":
        return []
    if "metrics" in topic:
        # incident shape (Phase 3.4): several metrics moved together
        return list(topic.get("metrics", []))
    if "metric" in topic:
        # single anomaly shape
        return [topic["metric"]]
    return []


def _is_incident(decision: Decision) -> bool:
    """
    True if this decision was about a correlated multi-metric incident
    (Phase 3.4), not a single anomaly or a user question.

    Checks topic.get("incident") is truthy AND topic.get("type") is
    NOT set, rather than a bare "incident" in topic membership test.
    Real incident dicts never have a "type" key -- only single-anomaly
    ("point_anomaly"/"trend_anomaly") and user_question topics do -- so
    requiring type to be absent guards against a malformed or
    unexpected topic shape that happens to carry a stray "incident"
    key (e.g. None, or empty string) from being misclassified as one.
    """
    evidence = decision.evidence or {}
    topic = evidence.get("topic", {}) or {}
    return bool(topic.get("incident")) and topic.get("type") is None


def run_report_agent(db: Session, company_id: int = 1, days: int = DEFAULT_REPORT_DAYS) -> dict:
    """
    Main function other code calls to use the Report Agent.

    Looks at every decision saved in the last `days` days for this
    company and summarizes:
      - which metrics kept coming up (recurring patterns)
      - how many were correlated incidents vs single-metric anomalies
      - how many got resolved, turned out to be false positives, were
        ignored, or are still sitting open unreviewed
      - a per-decision list, for anyone who wants the full detail
    """
    # NOTE: naive UTC to match the comparison style already used
    # elsewhere in this codebase (memory.py's is_duplicate_recent_decision
    # uses datetime.utcnow() the same way), so this compares cleanly
    # against Decision.created_at without a tz-aware/naive mismatch.
    cutoff = datetime.utcnow() - timedelta(days=days)

    decisions = (
        db.query(Decision)
        .filter(Decision.company_id == company_id)
        .filter(Decision.created_at >= cutoff)
        .order_by(Decision.created_at.desc())
        .all()
    )

    total = len(decisions)

    # --- recurring patterns: which metrics kept showing up ---
    metric_counts = {}
    incident_count = 0
    for decision in decisions:
        if _is_incident(decision):
            incident_count += 1
        for metric in _extract_metrics(decision):
            metric_counts[metric] = metric_counts.get(metric, 0) + 1

    # only metrics that showed up 2+ times count as an actual RECURRING
    # pattern -- a metric appearing once is just a normal single incident,
    # not a pattern
    recurring_patterns = [
        {"metric": metric, "occurrences": count}
        for metric, count in sorted(metric_counts.items(), key=lambda kv: kv[1], reverse=True)
        if count >= 2
    ]

    # --- resolved vs unresolved breakdown ---
    outcome_breakdown = {"resolved": 0, "false_positive": 0, "ignored": 0, "still_open": 0}
    for decision in decisions:
        if decision.outcome == "resolved":
            outcome_breakdown["resolved"] += 1
        elif decision.outcome == "false_positive":
            outcome_breakdown["false_positive"] += 1
        elif decision.outcome == "ignored":
            outcome_breakdown["ignored"] += 1
        else:
            outcome_breakdown["still_open"] += 1

    # resolution rate only counts decisions someone has actually reviewed
    # (matches the same logic dashboard.py's Step 6.3 rates use) --
    # still-open ones haven't been judged yet, so they shouldn't drag
    # the rate down just for not having been reviewed.
    reviewed_count = total - outcome_breakdown["still_open"]
    resolution_rate = (
        outcome_breakdown["resolved"] / reviewed_count if reviewed_count else None
    )

    average_confidence = (
        sum(decision.confidence for decision in decisions) / total if total else None
    )

    decision_summaries = [
        {
            "id": decision.id,
            "date": decision.created_at.isoformat() if decision.created_at else None,
            "metrics": _extract_metrics(decision),
            "is_incident": _is_incident(decision),
            "root_cause": decision.root_cause,
            "confidence": decision.confidence,
            "outcome": decision.outcome or "still_open",
        }
        for decision in decisions
    ]

    return {
        "agent": "report_agent",
        "period_days": days,
        "total_decisions": total,
        "incidents_detected": incident_count,
        "recurring_patterns": recurring_patterns,
        "outcome_breakdown": outcome_breakdown,
        "resolution_rate": round(resolution_rate, 3) if resolution_rate is not None else None,
        "average_confidence": round(average_confidence, 3) if average_confidence is not None else None,
        "decisions": decision_summaries,
    }