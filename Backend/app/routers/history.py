"""
routers/history.py

Shows a longer list of past decisions, and lets someone mark whether
a past decision actually helped (its outcome).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.memory import get_decision_history, mark_decision_outcome

router = APIRouter()

DEFAULT_COMPANY_ID = 1


def decision_to_dict(decision):
    return {
        "id": decision.id,
        "created_at": decision.created_at,
        "root_cause": decision.root_cause,
        "recommendation": decision.recommendation,
        "confidence": decision.confidence,
        "faithfulness_score": decision.faithfulness_score,
        "relevance_score": decision.relevance_score,
        "outcome": decision.outcome,
    }


@router.get("")
def get_history(db: Session = Depends(get_db)):
    decisions = get_decision_history(db, company_id=DEFAULT_COMPANY_ID, limit=50)
    return {"history": [decision_to_dict(d) for d in decisions]}


@router.post("/{decision_id}/outcome")
def set_outcome(decision_id: int, outcome: str, db: Session = Depends(get_db)):
    """
    outcome should be one of: "resolved", "false_positive", "ignored"
    """
    updated = mark_decision_outcome(db, decision_id, outcome)
    if updated is None:
        return {"success": False, "reason": "decision_not_found"}

    return {"success": True, "decision": decision_to_dict(updated)}