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
        # V2, Step 6.3: this was already being SAVED (Decision.relevance_score,
        # filled in by evaluate_decision()) but never actually shown on the
        # dashboard -- "Answer Relevancy" in the plan's metrics panel. Same
        # averaging pattern as faithfulness above.
        relevance_scores = [d.relevance_score for d in recent_decisions if d.relevance_score is not None]
        avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else None
    else:
        avg_confidence = None
        avg_faithfulness = None
        avg_relevance = None

    # V2, Step 6.3: resolution rate / false positive rate need a WIDER
    # window than the "last 20" above -- a decision needs time to
    # actually get reviewed and marked with an outcome, so only looking
    # at the most recent 20 would understate the rate (most of them
    # simply haven't been reviewed yet).
    RESOLUTION_WINDOW_LIMIT = 100
    resolution_window = (
        db.query(Decision)
        .filter(Decision.company_id == DEFAULT_COMPANY_ID)
        .order_by(Decision.created_at.desc())
        .limit(RESOLUTION_WINDOW_LIMIT)
        .all()
    )

    # only decisions someone has actually reviewed (outcome is not None)
    # count toward these rates -- still-open decisions haven't been
    # judged yet, so they shouldn't drag the rate down just because
    # nobody's gotten to them.
    closed_decisions = [d for d in resolution_window if d.outcome is not None]
    resolved_count = sum(1 for d in closed_decisions if d.outcome == "resolved")
    false_positive_count = sum(1 for d in closed_decisions if d.outcome == "false_positive")

    if closed_decisions:
        resolution_rate = resolved_count / len(closed_decisions)
        false_positive_rate = false_positive_count / len(closed_decisions)
    else:
        resolution_rate = None
        false_positive_rate = None

    return {
        "revenue_trend": revenue_trend,
        "open_alerts": open_alerts,
        "average_confidence": round(avg_confidence, 3) if avg_confidence is not None else None,
        "average_faithfulness": round(avg_faithfulness, 3) if avg_faithfulness is not None else None,
        "average_relevance": round(avg_relevance, 3) if avg_relevance is not None else None,
        "decisions_evaluated": len(recent_decisions),
        "resolution_rate": round(resolution_rate, 3) if resolution_rate is not None else None,
        "false_positive_rate": round(false_positive_rate, 3) if false_positive_rate is not None else None,
        "decisions_reviewed": len(closed_decisions),
        # V2, Step 6.3: NOT computable yet. run_decision_agent() already
        # calculates latency_seconds/tokens per call ("llm_info" in
        # decision_agent.py) and Logfire (Step 6.1) sees it live, but
        # nothing persists it onto the Decision row itself, so there's
        # no historical data to average here. Returning explicit nulls
        # + a note rather than silently omitting them or making up
        # numbers -- filling this in needs a small schema addition
        # (a column or two on Decision) plus updating memory.py's
        # save_decision() to actually store it, which is outside this
        # step's file scope (dashboard.py only).
        "average_llm_cost_usd": None,
        "average_latency_seconds": None,
        "cost_trend": None,
        "note": "average_llm_cost_usd, average_latency_seconds, and cost_trend need llm_info to be persisted on Decision rows first -- not yet stored anywhere.",
    }