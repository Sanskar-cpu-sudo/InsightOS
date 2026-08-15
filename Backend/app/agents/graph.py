from typing import TypedDict, Optional
from datetime import date

from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session

from app.agents.data_agent import run_data_agent
from app.agents.knowledge_agent import (
    run_knowledge_agent,
    run_knowledge_agent_from_anomaly,
    run_knowledge_agent_from_incident,
    find_recent_deployment,
    deployment_as_evidence,
)
from app.agents.decision_agent import run_decision_agent


class PipelineState(TypedDict):
    db: Session
    company_id: int
    mode: str                      # "auto" or "ask"
    user_question: Optional[str]

    data_agent_result: Optional[dict]
    chosen_anomaly: Optional[dict]
    chosen_incident: Optional[dict]  # V2, Step 3.4: set when correlated
    knowledge_agent_result: Optional[dict]
    decision_agent_result: Optional[dict]


def data_agent_node(state: PipelineState) -> PipelineState:
    """
    Only runs in "auto" mode. Finds anomalies in the sales data and
    picks the most important one to investigate further.
    """
    if state["mode"] != "auto":
        return state

    result = run_data_agent(state["db"], company_id=state["company_id"])
    state["data_agent_result"] = result

    anomalies = result["anomalies"]
    if not anomalies:
        state["chosen_anomaly"] = None
        state["chosen_incident"] = None
        return state

    # if there is more than one anomaly, pick the highest severity one first
    high_severity = [a for a in anomalies if a["severity"] == "high"]
    if high_severity:
        state["chosen_anomaly"] = high_severity[0]
    else:
        state["chosen_anomaly"] = anomalies[0]

    # V2, Step 3.4: also carry through the incident, if data_agent found
    # the anomalies to be correlated (Step 3.2's build_incident()).
    # chosen_anomaly above is left completely unchanged either way, so
    # any code still only reading chosen_anomaly behaves exactly as it
    # did in V1 -- this is purely additive.
    state["chosen_incident"] = result.get("incident")

    return state


def _incident_anomaly_time(incident: dict):
    """
    V2, Step 3.4: incidents don't have one single "date" the way a
    point_anomaly does -- they bundle several component anomalies
    together (data_agent.py's build_incident()). Look for a component
    with an exact date (a point_anomaly); fall back to today if the
    incident is made entirely of trend_anomalies, which have no single
    date of their own either.
    """
    for component in incident.get("anomalies", []):
        if component.get("date"):
            return component["date"]
    return date.today()


def knowledge_agent_node(state: PipelineState) -> PipelineState:
    """
    In "auto" mode: builds a search query from the chosen anomaly (or,
    V2 Step 3.4, from the whole INCIDENT when one was found -- covering
    every correlated metric's context instead of just one), AND (Step
    2.3) always checks for a recent deployment alongside it.
    In "ask" mode: searches directly using the user's question. There's
    no anomaly and no anomaly time in this mode, so the deployment check
    is skipped -- it has nothing to correlate against.
    """
    if state["mode"] == "auto":
        if state["chosen_anomaly"] is None:
            # nothing to search for, no anomaly was found
            state["knowledge_agent_result"] = None
            return state

        incident = state.get("chosen_incident")

        if incident is not None:
            # V2, Step 3.4: several metrics moved together -- search
            # using ALL of their context, not just the single anomaly
            # that happened to be picked as "chosen_anomaly" above.
            result = run_knowledge_agent_from_incident(
                incident,
                company_id=state["company_id"],
            )
            anomaly_time = _incident_anomaly_time(incident)
        else:
            # no correlation found -- exactly V1/Step-2.3 behavior
            anomaly = state["chosen_anomaly"]
            result = run_knowledge_agent_from_anomaly(
                anomaly,
                company_id=state["company_id"],
            )
            anomaly_time = anomaly.get("date", date.today())

        # V2, Step 2.3: ALWAYS run the targeted deployment lookup
        # alongside the semantic search, not just when the semantic
        # search happens to surface a deployment note by wording match.
        deployment = find_recent_deployment(state["db"], anomaly_time)

        if deployment is not None:
            # Put the deployment evidence FIRST -- it's a concrete,
            # checkable fact ("evidence_role": "temporal_signal"), not
            # just a similarity match, so it deserves to be the evidence
            # the Decision Agent sees first, not buried in the list.
            result["evidence"] = [deployment_as_evidence(deployment)] + result["evidence"]
            result["evidence_found"] = len(result["evidence"])
    else:
        result = run_knowledge_agent(
            state["user_question"],
            company_id=state["company_id"],
        )

    state["knowledge_agent_result"] = result
    return state


def decision_agent_node(state: PipelineState) -> PipelineState:
    """
    Takes whatever the Data Agent and Knowledge Agent found and produces
    the final explanation and recommendation.
    """
    if state["knowledge_agent_result"] is None:
        state["decision_agent_result"] = None
        return state

    evidence = state["knowledge_agent_result"]["evidence"]

    if state["mode"] == "auto":
        # V2, Step 3.4: prefer the incident when one was found -- it's
        # the fuller picture when several metrics moved together.
        # Falls back to chosen_anomaly exactly like V1 did whenever
        # there's no incident (the common, single-metric case).
        anomaly = state.get("chosen_incident") or state["chosen_anomaly"]
    else:
        # in "ask" mode there is no anomaly from the Data Agent,
        # so we build a simple stand-in describing the user's question
        anomaly = {
            "type": "user_question",
            "question": state["user_question"],
        }

    result = run_decision_agent(anomaly, evidence)
    state["decision_agent_result"] = result
    return state


def build_graph():
    """
    Builds and compiles the LangGraph pipeline.
    This only needs to be called once - the compiled graph can be reused
    for every run.
    """
    graph = StateGraph(PipelineState)

    graph.add_node("data_agent", data_agent_node)
    graph.add_node("knowledge_agent", knowledge_agent_node)
    graph.add_node("decision_agent", decision_agent_node)

    graph.add_edge(START, "data_agent")
    graph.add_edge("data_agent", "knowledge_agent")
    graph.add_edge("knowledge_agent", "decision_agent")
    graph.add_edge("decision_agent", END)

    return graph.compile()


# built once, reused everywhere
compiled_graph = build_graph()


def run_pipeline_auto(db: Session, company_id: int = 1) -> PipelineState:
    """
    Runs the full pipeline in automatic mode (used by the hourly scheduler).
    Starts from the Data Agent scanning for anomalies on its own.
    """
    initial_state: PipelineState = {
        "db": db,
        "company_id": company_id,
        "mode": "auto",
        "user_question": None,
        "data_agent_result": None,
        "chosen_anomaly": None,
        "chosen_incident": None,
        "knowledge_agent_result": None,
        "decision_agent_result": None,
    }
    return compiled_graph.invoke(initial_state)


def run_pipeline_ask(db: Session, question: str, company_id: int = 1) -> PipelineState:
    """
    Runs the pipeline in on-demand mode, starting from a user's question
    instead of an automatically detected anomaly. Skips the Data Agent.
    """
    initial_state: PipelineState = {
        "db": db,
        "company_id": company_id,
        "mode": "ask",
        "user_question": question,
        "data_agent_result": None,
        "chosen_anomaly": None,
        "chosen_incident": None,
        "knowledge_agent_result": None,
        "decision_agent_result": None,
    }
    return compiled_graph.invoke(initial_state)