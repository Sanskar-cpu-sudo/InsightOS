"""
routers/dashboard.py

One endpoint that gives the frontend everything it needs to show the
main Dashboard page: recent revenue, how many alerts are open, and
average evaluation scores.
"""

from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Sale, Decision

router = APIRouter()

DEFAULT_COMPANY_ID = 1


@router.get("")
def get_dashboard(db: Session = Depends(get_db)):
    # last 7 days of sales, for a simple revenue trend
    start_date = date.today() - timedelta(days=7)
    recent_sales = (
        db.query(Sale)
        .filter(Sale.company_id == DEFAULT_COMPANY_ID)
        .filter(Sale.date >= start_date)
        .order_by(Sale.date)
        .all()
    )

    revenue_trend = [
        {"date": str(s.date), "revenue": s.revenue} for s in recent_sales
    ]

    # how many decisions are still open (not marked resolved yet)
    open_alerts = (
        db.query(Decision)
        .filter(Decision.company_id == DEFAULT_COMPANY_ID)
        .filter(Decision.outcome.is_(None))
        .count()
    )

    # average evaluation scores across the last 20 decisions
    recent_decisions = (
        db.query(Decision)
        .filter(Decision.company_id == DEFAULT_COMPANY_ID)
        .order_by(Decision.created_at.desc())
        .limit(20)
        .all()
    )

    if recent_decisions:
        avg_confidence = sum(d.confidence for d in recent_decisions) / len(recent_decisions)
        faithfulness_scores = [d.faithfulness_score for d in recent_decisions if d.faithfulness_score is not None]
        avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else None
    else:
        avg_confidence = None
        avg_faithfulness = None

    return {
        "revenue_trend": revenue_trend,
        "open_alerts": open_alerts,
        "average_confidence": round(avg_confidence, 3) if avg_confidence is not None else None,
        "average_faithfulness": round(avg_faithfulness, 3) if avg_faithfulness is not None else None,
        "decisions_evaluated": len(recent_decisions),
    }