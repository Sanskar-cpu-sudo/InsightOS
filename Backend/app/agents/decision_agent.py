from app.llm_gateway import complete_json


SYSTEM_PROMPT = """
You are a business analyst AI. You are given:
1. An anomaly found in a company's numbers (like a sales drop)
2. A list of evidence pieces (support tickets, reviews, deployment notes, or policy documents)

Your job is to explain the most likely root cause by connecting the anomaly
to the evidence. Only use the evidence given to you. Do not make up facts
that are not in the evidence.

You must respond with a JSON object in exactly this format:

{
  "root_cause": "one or two sentences explaining what most likely caused this",
  "evidence_used": ["short quote or summary of each evidence piece you actually used"],
  "confidence": 0.0 to 1.0,
  "recommendation": "one clear recommended action",
  "business_impact": "one sentence describing the likely impact if nothing is done"
}

Rules:
- confidence should be LOW (below 0.4) if the evidence is weak or unrelated
- confidence should be HIGH (above 0.8) only if the evidence clearly supports the root_cause
- if there is not enough evidence to explain the anomaly, say so honestly in root_cause
  and set confidence low, instead of guessing
"""


def build_user_prompt(anomaly: dict, evidence: list) -> str:
    """
    Turns the anomaly and evidence into plain text that we send to the LLM.

    Note: we do NOT include the relevance_score here on purpose. That score
    comes from the retrieval system (how close the text matched the search
    query), not from the actual business data. Showing it to the LLM could
    make it over-trust a high score instead of judging the evidence on its
    own content. The score is still kept in the evidence list for logging
    and for showing in the UI later -- just not sent into the prompt.
    """
    if anomaly.get("type") == "user_question":
        intro_text = f"User question:\n{anomaly.get('question', '')}\n\n"
    else:
        intro_text = f"Anomaly detected:\n{anomaly}\n\n"

    if not evidence:
        evidence_text = "No supporting evidence was found.\n"
    else:
        evidence_text = "Evidence:\n"
        for i, item in enumerate(evidence, start=1):
            source_label = item["source_type"].capitalize()
            evidence_text += f"{i}. [{source_label}] {item['text']}\n"

    return intro_text + evidence_text


def run_decision_agent(anomaly: dict, evidence: list) -> dict:
    """
    Main function other code calls to use the Decision Agent.

    anomaly: one anomaly dict from the Data Agent
    evidence: the evidence list from the Knowledge Agent

    Returns a dict with root_cause, evidence_used, confidence,
    recommendation, and business_impact. If the LLM call fails
    completely, returns a dict with an "error" key instead.
    """
    user_prompt = build_user_prompt(anomaly, evidence)

    result, llm_response = complete_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
    )

    # if complete_json() failed (bad JSON or LLM gateway down), it returns
    # a dict with an "error" key -- just pass that straight through
    if "error" in result:
        return {
            "agent": "decision_agent",
            "success": False,
            "error": result["error"],
        }

    # attach some extra info that is useful later (latency, tokens, model used)
    llm_info = {}
    if llm_response is not None:
        llm_info = {
            "model_used": llm_response.model,
            "latency_seconds": llm_response.latency_seconds,
            "input_tokens": llm_response.input_tokens,
            "output_tokens": llm_response.output_tokens,
        }

    return {
        "agent": "decision_agent",
        "success": True,
        "root_cause": result.get("root_cause", ""),
        "evidence_used": result.get("evidence_used", []),
        "confidence": result.get("confidence", 0.0),
        "recommendation": result.get("recommendation", ""),
        "business_impact": result.get("business_impact", ""),
        "llm_info": llm_info,
    }