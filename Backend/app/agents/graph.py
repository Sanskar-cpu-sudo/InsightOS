from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session

from app.agents.data_agent import run_data_agent
from app.agents.knowledge_agent import run_knowledge_agent, run_knowledge_agent_from_anomaly
from app.agents.decision_agent import run_decision_agent


class PipelineState(TypedDict):
    db: Session
    company_id: int
    mode: str                      # "auto" or "ask"
    user_question: Optional[str]

    data_agent_result: Optional[dict]
    chosen_anomaly: Optional[dict]
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
        return state

    # if there is more than one anomaly, pick the highest severity one first
    high_severity = [a for a in anomalies if a["severity"] == "high"]
    if high_severity:
        state["chosen_anomaly"] = high_severity[0]
    else:
        state["chosen_anomaly"] = anomalies[0]

    return state


def knowledge_agent_node(state: PipelineState) -> PipelineState:
    """
    In "auto" mode: builds a search query from the chosen anomaly.
    In "ask" mode: searches directly using the user's question.
    """
    if state["mode"] == "auto":
        if state["chosen_anomaly"] is None:
            # nothing to search for, no anomaly was found
            state["knowledge_agent_result"] = None
            return state

        result = run_knowledge_agent_from_anomaly(
            state["chosen_anomaly"],
            company_id=state["company_id"],
        )
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
        anomaly = state["chosen_anomaly"]
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
        "knowledge_agent_result": None,
        "decision_agent_result": None,
    }
    return compiled_graph.invoke(initial_state)