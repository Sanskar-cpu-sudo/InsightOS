import os
import re
from datetime import datetime, UTC

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


# V2, Step 4.2: how old evidence has to be before recency language
# ("currently", "recently", "ongoing") counts as misleading. Kept as a
# local constant (not in config.py) to stay within this step's scope --
# can be promoted to a setting later if it needs to be tuned per-env.
STALE_EVIDENCE_DAYS = 14

# words that, if the answer uses them, are claiming the situation is
# happening RIGHT NOW -- not just that it happened at some point
RECENCY_CLAIM_WORDS = ["currently", "recently", "right now", "ongoing", "as of today", "this week"]

# words that, if the answer uses them, are blaming a deployment/release
# for the problem -- a strong, checkable causal claim
DEPLOYMENT_CLAIM_WORDS = ["deploy", "deployment", "release", "rollout", "shipped"]

# phrases that, if the answer uses them, are crediting a specific TYPE
# of source ("reviews show...") -- checked against what evidence
# actually contains that source_type
SOURCE_TYPE_CLAIM_PHRASES = {
    "review": ["review", "reviews"],
    "ticket": ["ticket", "tickets", "support ticket"],
    "deployment": ["deployment", "deploy ", "deployed", "release"],
    "document": ["document", "policy document", "uploaded document"],
}


def _freshest_evidence_age_days(evidence: list) -> float | None:
    """
    Returns how many days old the NEWEST piece of evidence in the list
    is, or None if nothing in the list has a usable created_at.
    """
    now = datetime.now(UTC)
    newest_age_days = None

    for item in evidence:
        created_at = item.get("created_at")
        if not created_at:
            continue
        try:
            created_dt = (
                datetime.fromisoformat(created_at)
                if isinstance(created_at, str)
                else created_at
            )
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=UTC)
            age_days = (now - created_dt).total_seconds() / 86400
        except (ValueError, TypeError):
            continue

        if newest_age_days is None or age_days < newest_age_days:
            newest_age_days = age_days

    return newest_age_days


def check_evidence_safety(decision_result: dict, evidence: list) -> dict:
    """
    Phase 4, Step 4.2: the NEW evidence-safety checks -- the category
    the plan calls out as most important for us. These don't check
    "is the wording safe" (that's what the self-check LLM rails in
    check_input/check_output do) -- they check whether the ANSWER
    actually matches what the evidence really says, using the
    evidence_role/created_at metadata Phases 1-2 attached to each item.

    All four checks here are fast, structural, and deterministic -- no
    LLM call involved, so they run instantly and can't be talked around
    the way a wording-based LLM check sometimes can be.

    Returns {"passed": True} if nothing looks wrong, or
    {"passed": False, "reason": "..."} for the FIRST problem found.
    """
    root_cause = decision_result.get("root_cause", "") or ""
    recommendation = decision_result.get("recommendation", "") or ""
    evidence_used = decision_result.get("evidence_used", []) or []
    combined_text = f"{root_cause} {recommendation}".lower()

    # --- Check 1: claim has no evidence ---
    # If the Knowledge Agent found NOTHING at all, the Decision Agent
    # cannot legitimately claim to have used any. Claiming otherwise
    # means it fabricated a citation out of nothing.
    if not evidence and evidence_used:
        return {"passed": False, "reason": "evidence_fabricated_none_available"}

    # --- Check 2: claim contradicts evidence (fabricated source type) ---
    # If the answer explicitly credits a TYPE of source ("reviews
    # show...", "tickets indicate...") that isn't actually present
    # anywhere in the evidence we retrieved, that's citing a source
    # that doesn't exist for this case -- a factual contradiction.
    available_source_types = {item.get("source_type") for item in evidence}
    for source_type, phrases in SOURCE_TYPE_CLAIM_PHRASES.items():
        mentioned = any(phrase in combined_text for phrase in phrases)
        if mentioned and source_type not in available_source_types:
            return {"passed": False, "reason": f"evidence_contradicts_claim_no_{source_type}_evidence"}

    # --- Check 3: old evidence presented as current ---
    # If the answer uses recency language ("currently", "ongoing", ...)
    # but the freshest evidence it actually had access to is stale,
    # that's misleading -- it implies a live, ongoing situation off of
    # data that may no longer reflect reality.
    claims_recency = any(word in combined_text for word in RECENCY_CLAIM_WORDS)
    if claims_recency and evidence:
        newest_age_days = _freshest_evidence_age_days(evidence)
        if newest_age_days is not None and newest_age_days > STALE_EVIDENCE_DAYS:
            return {"passed": False, "reason": "old_evidence_presented_as_current"}

    # --- Check 4: deployment claimed as cause without temporal evidence ---
    # Blaming a deployment/release for the problem is a strong, checkable
    # causal claim -- it should only be made when a real
    # find_recent_deployment() match backs it up ("evidence_role":
    # "temporal_signal", Phase 2), not just because a deployment note
    # happened to surface via ordinary semantic-similarity search.
    claims_deployment_cause = any(word in combined_text for word in DEPLOYMENT_CLAIM_WORDS)
    has_temporal_signal = any(item.get("evidence_role") == "temporal_signal" for item in evidence)
    if claims_deployment_cause and not has_temporal_signal:
        return {"passed": False, "reason": "deployment_claimed_without_temporal_evidence"}

    return {"passed": True}


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


def check_output(decision_result: dict, evidence: list | None = None) -> dict:
    """
    Runs after the Decision Agent produces its answer.
    Returns {"passed": True} if it is safe to show to the user,
    or {"passed": False, "reason": "..."} if it should be blocked.

    V2, Step 4.2: `evidence` is a new, OPTIONAL parameter -- pass the
    evidence list the Decision Agent actually saw (from the Knowledge
    Agent's result) to also run the new evidence-safety checks
    (check_evidence_safety() above). Left as None by default so any
    existing caller that doesn't pass it yet keeps working exactly as
    before; it just skips those checks until it's wired through.
    """
    if not decision_result.get("success"):
        return {"passed": False, "reason": "decision_agent_failed"}

    root_cause = decision_result.get("root_cause", "")
    recommendation = decision_result.get("recommendation", "")
    confidence = decision_result.get("confidence", 0)
    evidence_used = decision_result.get("evidence_used", [])
    combined_text = f"{root_cause} {recommendation}"

    # Layer 2 - our own simple structural checks (fast, free, no LLM)

    # V2, Step 4.3: split into separate reasons instead of one bundled
    # "missing_required_fields" -- this is its own category in the plan
    # ("missing recommendation"), and separate reasons are more useful
    # for debugging/monitoring which piece is actually going wrong.
    if not root_cause:
        return {"passed": False, "reason": "missing_root_cause"}

    if not recommendation:
        return {"passed": False, "reason": "missing_recommendation"}

    # V2, Step 4.3: this used to only check the TYPE of confidence, not
    # its RANGE -- a confidence of 5.0 or -3 would have passed silently.
    # "invalid confidence" (from the plan) means both.
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return {"passed": False, "reason": "invalid_confidence_type"}

    if not (0.0 <= confidence <= 1.0):
        return {"passed": False, "reason": "invalid_confidence_range"}

    if not evidence_used:
        return {"passed": False, "reason": "missing_evidence"}

    if confidence < settings.MIN_CONFIDENCE_TO_SHOW:
        return {"passed": False, "reason": "confidence_too_low"}

    # V2, Step 4.3: unsupported certainty -- a high confidence score
    # should actually be backed by more than a single piece of evidence,
    # and confident-sounding WORDING should actually match how confident
    # the model itself claims to be. Either mismatch means the answer is
    # overclaiming relative to what it really has.
    if confidence >= 0.85 and len(evidence_used) < 2:
        return {"passed": False, "reason": "unsupported_certainty_thin_evidence"}

    absolute_certainty_words = [
        "definitely", "100%", "guaranteed", "certainly",
        "without a doubt", "undoubtedly", "proven fact",
    ]
    text_lower = combined_text.lower()
    uses_absolute_language = any(word in text_lower for word in absolute_certainty_words)
    if uses_absolute_language and confidence < 0.95:
        return {"passed": False, "reason": "unsupported_certainty_language"}

    # V2, Step 4.3: fast structural pre-checks for unsafe content, ahead
    # of the LLM-based check below -- these are cheap, deterministic
    # patterns that don't need an LLM's judgment to catch.
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    phone_pattern = r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    if re.search(email_pattern, combined_text) or re.search(phone_pattern, combined_text):
        return {"passed": False, "reason": "unsafe_content_pii_detected"}

    # a few distinctive phrases from decision_agent.py's SYSTEM_PROMPT --
    # if the answer echoes these back, the system prompt itself has
    # leaked into the output rather than being followed silently
    prompt_leak_phrases = [
        "you are a business analyst ai",
        "respond with a json object",
        "root_cause",
    ]
    if any(phrase in text_lower for phrase in prompt_leak_phrases):
        return {"passed": False, "reason": "unsafe_content_prompt_leak"}

    # V2, Step 4.2: evidence-safety checks -- also fast/structural, no
    # LLM call, so they run right alongside Layer 2 above. Only runs
    # when a caller actually passes `evidence` in.
    if evidence is not None:
        evidence_safety_result = check_evidence_safety(decision_result, evidence)
        if not evidence_safety_result["passed"]:
            return evidence_safety_result

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