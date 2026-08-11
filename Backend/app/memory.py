"""
memory.py

This is the Decision Memory. It is in charge of saving decisions to
the database, and reading them back later.

It also has ONE important rule: if the same problem was already
reported recently and nothing has changed, we do NOT save a brand new
duplicate decision every single hour. Instead we just skip saving it
again. This stops the decisions table from filling up with the same
issue repeated 24 times a day.

"Same problem" here means: same metric (like "revenue"), found within
the last 24 hours, and not yet marked as resolved.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models import Decision

DUPLICATE_CHECK_HOURS = 24


def is_duplicate_recent_decision(db: Session, company_id: int, metric: str) -> bool:
    """
    Checks if there is already a recent decision about the same metric
    that has not been marked resolved yet.

    Returns True if this is a duplicate (should NOT save a new one).
    Returns False if this is a new/different issue (should save it).
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=DUPLICATE_CHECK_HOURS)

    existing = (
        db.query(Decision)
        .filter(Decision.company_id == company_id)
        .filter(Decision.created_at >= cutoff_time)
        .filter(Decision.outcome.is_(None))  # not yet resolved
        .all()
    )

    for decision in existing:
        # we stored the metric name inside the evidence field when we
        # saved the decision, so we check it here
        if decision.evidence.get("metric") == metric:
            return True

    return False


def save_decision(
    db: Session,
    company_id: int,
    topic: dict,
    decision_result: dict,
    evaluation_scores: dict,
) -> Decision | None:
    """
    Saves a new decision to the database, unless it is a duplicate of
    something already reported recently.

    topic: the anomaly dict (or user question stand-in) this decision is about
    decision_result: the dict from run_decision_agent()
    evaluation_scores: the dict from evaluate_decision()

    Returns the saved Decision row, or None if it was skipped as a duplicate.
    """
    metric = topic.get("metric", "unknown")

    if topic.get("type") != "user_question":
        if is_duplicate_recent_decision(db, company_id, metric):
            return None

    new_decision = Decision(
        company_id=company_id,
        root_cause=decision_result.get("root_cause", ""),
        evidence={
            "metric": metric,
            "topic": topic,
            "evidence_used": decision_result.get("evidence_used", []),
        },
        confidence=decision_result.get("confidence", 0.0),
        recommendation=decision_result.get("recommendation", ""),
        groundedness_score=evaluation_scores.get("faithfulness_score"),
        faithfulness_score=evaluation_scores.get("faithfulness_score"),
        relevance_score=evaluation_scores.get("relevance_score"),
    ) 

    db.add(new_decision)
    db.commit()
    db.refresh(new_decision)

    return new_decision


def get_latest_decisions(db: Session, company_id: int, limit: int = 10):
    """
    Used by the Dashboard and Recommendations page - gets the most
    recent decisions, newest first.
    """
    return (
        db.query(Decision)
        .filter(Decision.company_id == company_id)
        .order_by(Decision.created_at.desc())
        .limit(limit)
        .all()
    )


def get_decision_history(db: Session, company_id: int, limit: int = 50):
    """
    Used by the History page - gets a longer list of past decisions.
    """
    return (
        db.query(Decision)
        .filter(Decision.company_id == company_id)
        .order_by(Decision.created_at.desc())
        .limit(limit)
        .all()
    )


def mark_decision_outcome(db: Session, decision_id: int, outcome: str) -> Decision | None:
    """
    Lets someone mark whether a past decision actually helped.
    outcome should be one of: "resolved", "false_positive", "ignored"
    """
    decision = db.query(Decision).filter(Decision.id == decision_id).first()
    if decision is None:
        return None

    decision.outcome = outcome
    db.commit()
    db.refresh(decision)

    return decision