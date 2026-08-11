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
    """Turns a Decision database row into a plain dict for the API response."""
    return {
        "id": decision.id,
        "created_at": decision.created_at,
        "root_cause": decision.root_cause,
        "recommendation": decision.recommendation,
        "confidence": decision.confidence,
        "evidence": decision.evidence,
        "faithfulness_score": decision.faithfulness_score,
        "relevance_score": decision.relevance_score,
        "outcome": decision.outcome,
    }


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

    # LAYER 2: check the answer is safe/complete before showing it
    output_check = check_output(decision_result)
    if not output_check["passed"]:
        return {"success": False, "reason": output_check["reason"]}

    # build a proper FACTUAL sentence about the anomaly (not a question)
    # so faithfulness checking can actually verify revenue/metric claims
    topic_statement = anomaly_to_statement(chosen_anomaly)

    evidence = result_state["knowledge_agent_result"]["evidence"]
    evaluation_scores = evaluate_decision(decision_result, evidence, topic_statement)

    saved_decision = save_decision(
        db, DEFAULT_COMPANY_ID, chosen_anomaly, decision_result, evaluation_scores
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

    # LAYER 2: check the answer is safe/complete before showing it
    output_check = check_output(decision_result)
    if not output_check["passed"]:
        return {"success": False, "reason": output_check["reason"]}

    # score the answer quality using RAGAS
    evidence = result_state["knowledge_agent_result"]["evidence"]
    evaluation_scores = evaluate_decision(decision_result, evidence, question)

    # save it to Decision Memory
    topic = {"type": "user_question", "question": question, "metric": "user_question"}
    saved_decision = save_decision(db, DEFAULT_COMPANY_ID, topic, decision_result, evaluation_scores)

    return {
        "success": True,
        "decision": decision_to_dict(saved_decision) if saved_decision else decision_result,
    }