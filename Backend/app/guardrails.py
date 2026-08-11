import os
from langchain_groq import ChatGroq
from nemoguardrails import RailsConfig, LLMRails
from nemoguardrails.llm.providers import register_chat_provider

from app.config import get_settings

settings = get_settings()

# IMPORTANT: NeMo Guardrails does NOT support Groq out of the box, even
# with langchain-groq installed. We have to manually tell it that
# "groq" (the name we use in config.yml) means "use ChatGroq". This
# must run BEFORE we load the rails config below.
register_chat_provider("groq", ChatGroq)

# ChatGroq reads its API key from this environment variable.
if settings.GROQ_API_KEY:
    os.environ["GROQ_API_KEY"] = settings.GROQ_API_KEY

# This is the exact default message NeMo Guardrails sends back when a
# self check rail blocks something. We check for this to know a block
# happened.
REFUSAL_MESSAGE = "I'm sorry, I can't respond to that."

# Load the NeMo Guardrails config once, reuse it everywhere.
# We build the path from this file's own location so it works no
# matter which folder the app is started from.
_config_path = os.path.join(os.path.dirname(__file__), "guardrails_config")
_rails_config = RailsConfig.from_path(_config_path)
_rails = LLMRails(_rails_config)


def check_input(user_question: str) -> dict:
    """
    Runs before we search for evidence or call the Decision Agent.
    Returns {"passed": True} if the question is okay to process,
    or {"passed": False, "reason": "..."} if it should be blocked.
    """
    # quick, free checks first - no need to call an LLM for these
    if user_question is None or user_question.strip() == "":
        return {"passed": False, "reason": "empty_question"}

    if len(user_question.strip()) < 5:
        return {"passed": False, "reason": "question_too_short"}

    # now run it through NeMo Guardrails' "self check input" rail
    response = _rails.generate(messages=[
        {"role": "user", "content": user_question}
    ])

    reply_text = response.get("content", "") if isinstance(response, dict) else str(response)

    if REFUSAL_MESSAGE in reply_text:
        return {"passed": False, "reason": "blocked_by_input_guardrail"}

    return {"passed": True}


def check_output(decision_result: dict) -> dict:
    """
    Runs after the Decision Agent produces its answer.
    Returns {"passed": True} if it is safe to show to the user,
    or {"passed": False, "reason": "..."} if it should be blocked.
    """
    if not decision_result.get("success"):
        return {"passed": False, "reason": "decision_agent_failed"}

    root_cause = decision_result.get("root_cause", "")
    recommendation = decision_result.get("recommendation", "")
    confidence = decision_result.get("confidence", 0)
    evidence_used = decision_result.get("evidence_used", [])

    # Layer 2 first - our own simple structural checks (fast, free, no LLM)
    if not root_cause or not recommendation:
        return {"passed": False, "reason": "missing_required_fields"}

    if not isinstance(confidence, (int, float)):
        return {"passed": False, "reason": "invalid_confidence_type"}

    if not evidence_used:
        return {"passed": False, "reason": "no_evidence_used"}

    if confidence < settings.MIN_CONFIDENCE_TO_SHOW:
        return {"passed": False, "reason": "confidence_too_low"}

    # Layer 1 - NeMo Guardrails checks the actual wording of the answer.
    # We ask it to check the combined root_cause + recommendation text.
    combined_answer = f"{root_cause} {recommendation}"

    response = _rails.generate(messages=[
        {"role": "user", "content": "Please check this answer."},
        {"role": "assistant", "content": combined_answer},
    ])

    reply_text = response.get("content", "") if isinstance(response, dict) else str(response)

    if REFUSAL_MESSAGE in reply_text:
        return {"passed": False, "reason": "blocked_by_output_guardrail"}

    return {"passed": True}