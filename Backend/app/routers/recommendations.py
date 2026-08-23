"""
routers/recommendations.py

Two endpoints here:

GET  /recommendations       -> shows the latest decisions the system
                                already made on its own (from the
                                hourly automatic pipeline)

POST /recommendations/ask   -> lets the user type a question and get
                                an answer right now (on-demand mode)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.agents.graph import run_pipeline_ask, run_pipeline_auto
from app.evaluation import evaluate_decision, anomaly_to_statement
from app.guardrails import check_input, check_output
from app.memory import get_latest_decisions, save_decision

router = APIRouter()

DEFAULT_COMPANY_ID = 1


def decision_to_dict(decision):
    """
    Turns a Decision database row into a plain dict for the API response.
    Delegates to Decision.to_dict() (models.py) for the NaN-safe fields
    shared with history.py, and adds "evidence" -- the one extra field
    this router's responses include that history.py's don't.
    """
    return {**decision.to_dict(), "evidence": decision.evidence}


@router.get("")
def get_recommendations(db: Session = Depends(get_db)):
    """Returns the latest decisions found automatically by the hourly pipeline."""
    decisions = get_latest_decisions(db, company_id=DEFAULT_COMPANY_ID, limit=10)
    return {"recommendations": [decision_to_dict(d) for d in decisions]}


@router.post("/run-now")
def run_auto_pipeline_now(db: Session = Depends(get_db)):
    """
    Manually triggers the automatic pipeline (Data Agent -> Knowledge
    Agent -> Decision Agent), the same thing the hourly scheduler will
    eventually call on its own. Useful for testing right now, since we
    haven't built the scheduler yet.

    This is the step that was MISSING before: evaluate_decision() now
    actually gets called for automatic decisions too, not just for
    /ask questions.
    """
    result_state = run_pipeline_auto(db, company_id=DEFAULT_COMPANY_ID)

    chosen_anomaly = result_state["chosen_anomaly"]
    decision_result = result_state["decision_agent_result"]

    if chosen_anomaly is None or decision_result is None:
        return {"success": False, "reason": "no_anomaly_found"}

    # BUG FIX: this used to always save `chosen_anomaly`, even when the
    # anomalies were actually CORRELATED into an incident (Phase 3.4).
    # graph.py's decision_agent_node already prefers chosen_incident
    # internally when reasoning -- this line makes what gets PERSISTED
    # (and shown via /recommendations, /history) match that same
    # preference, instead of silently reverting to the single-metric
    # shape regardless of what the Decision Agent actually reasoned
    # about.
    topic = result_state.get("chosen_incident") or chosen_anomaly

    # V2 FIX: this was computed AFTER check_output() ran, so it was
    # never actually passed in -- meaning the Phase 4.2 evidence-safety
    # checks (fabricated evidence, stale evidence presented as current,
    # deployment blamed without a real temporal_signal match) were
    # fully built and tested, but never active on live traffic. Moving
    # this line up so it's available for the check below.
    evidence = result_state["knowledge_agent_result"]["evidence"]

    # LAYER 2: check the answer is safe/complete before showing it.
    # Passing `evidence` in activates the evidence-safety checks
    # (check_evidence_safety() in guardrails.py) alongside the
    # structural ones.
    output_check = check_output(decision_result, evidence=evidence)
    if not output_check["passed"]:
        return {"success": False, "reason": output_check["reason"]}

    # build a proper FACTUAL sentence about the anomaly/incident (not a
    # question) so faithfulness checking can actually verify revenue/metric
    # claims against it
    topic_statement = anomaly_to_statement(topic)

    evaluation_scores = evaluate_decision(decision_result, evidence, topic_statement)

    saved_decision = save_decision(
        db, DEFAULT_COMPANY_ID, topic, decision_result, evaluation_scores
    )

    if saved_decision is None:
        return {"success": True, "reason": "duplicate_skipped_recent_decision_exists"}

    return {"success": True, "decision": decision_to_dict(saved_decision)}


@router.post("/ask")
def ask_question(question: str, db: Session = Depends(get_db)):
    """
    Lets a user ask a direct question, like "why did sales drop".
    Runs the same pipeline as the automatic mode, but starting from
    the question instead of an automatically found anomaly.
    """
    # LAYER 1: check the question is safe/allowed before doing any work
    input_check = check_input(question)
    if not input_check["passed"]:
        return {"success": False, "reason": input_check["reason"]}

    # run the pipeline (Knowledge Agent -> Decision Agent)
    result_state = run_pipeline_ask(db, question, company_id=DEFAULT_COMPANY_ID)
    decision_result = result_state["decision_agent_result"]

    if decision_result is None:
        return {"success": False, "reason": "no_evidence_found"}

    # V2 FIX: same issue as run_auto_pipeline_now above -- this was
    # computed after check_output() ran, so evidence-safety checks
    # were never actually active here either. Moved up.
    evidence = result_state["knowledge_agent_result"]["evidence"]

    # LAYER 2: check the answer is safe/complete before showing it
    output_check = check_output(decision_result, evidence=evidence)
    if not output_check["passed"]:
        return {"success": False, "reason": output_check["reason"]}

    # score the answer quality using RAGAS
    evaluation_scores = evaluate_decision(decision_result, evidence, question)

    # save it to Decision Memory
    topic = {"type": "user_question", "question": question, "metric": "user_question"}
    saved_decision = save_decision(db, DEFAULT_COMPANY_ID, topic, decision_result, evaluation_scores)

    return {
        "success": True,
        "decision": decision_to_dict(saved_decision) if saved_decision else decision_result,
    }