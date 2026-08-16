"""
routers/reports.py

Phase 7, Step 7.2: exposes the Report Agent (agents/report_agent.py)
as GET /reports/weekly -- a look back at the last 7 days of Decision
Memory: what kept coming up, which of it was a correlated incident,
and how much actually got resolved.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.agents.report_agent import run_report_agent, DEFAULT_REPORT_DAYS

router = APIRouter()

DEFAULT_COMPANY_ID = 1


@router.get("/weekly")
def get_weekly_report(days: int = DEFAULT_REPORT_DAYS, db: Session = Depends(get_db)):
    """
    Returns a summary of Decision Memory over the last `days` days
    (defaults to 7, hence "weekly" -- but callable with a different
    window via ?days=14 etc. without needing a new endpoint).
    """
    return run_report_agent(db, company_id=DEFAULT_COMPANY_ID, days=days)