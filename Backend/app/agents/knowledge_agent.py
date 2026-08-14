"""
knowledge_agent.py

This is the Knowledge Agent.
Its job is to search through text data (support tickets, reviews,
uploaded documents, deployment notes) and find the pieces that are
related to a problem.

It does not decide WHY something happened. It just finds evidence.
The Decision Agent is the one that explains WHY, using this evidence.

This agent can be used in two ways:
1. Given an anomaly from the Data Agent (automatic mode)
2. Given a direct question from a user (on-demand mode)
"""

from app.vector_store import search
from app.config import get_settings

settings = get_settings()


# For each metric, we list out the kinds of real-world causes that
# usually explain a change in that metric. This gives the embedding
# model much more context to match against, instead of one short
# generic sentence. More context = better matching tickets/reviews found.
METRIC_CONTEXT = {
    "revenue": (
        "customer complaints about checkout, payment failures, slow website, "
        "app crashes, pricing changes, discount or promotion changes, "
        "inventory or stock problems, deployment or release changes, "
        "marketing campaign changes, competitor activity"
    ),
    "orders": (
        "checkout problems, payment failures, cart abandonment, "
        "slow website, app crashes, shipping delays, "
        "product availability issues, pricing or discount changes"
    ),
    "avg_order_value": (
        "pricing changes, discount or coupon changes, "
        "product mix changes, upsell or bundle changes, "
        "customer downgrading purchases"
    ),
}


def build_query_from_anomaly(anomaly: dict) -> str:
    """
    Takes an anomaly dict from the Data Agent and turns it into a rich
    text search query -- not just a short generic sentence.

    Why rich: a short query like "revenue dropped 30 percent" does not
    give the embedding model much to match against. A richer query that
    lists the KINDS of things that usually cause this metric to change
    (checkout issues, payment issues, deployments, pricing, etc.) helps
    Qdrant find tickets and reviews that are actually related, even if
    they don't use the word "revenue" anywhere.

    Example output:
        "Recent customer complaints, payment issues, checkout failures,
        deployment changes, pricing changes, inventory problems, or
        marketing events related to revenue decline of -32.5 percent."
    """
    metric = anomaly.get("metric", "business metric")
    change = anomaly.get("percent_change", anomaly.get("total_percent_change", ""))
    direction = "decline" if str(change).startswith("-") else "change"

    context = METRIC_CONTEXT.get(metric, "")

    if anomaly.get("type") == "trend_anomaly":
        query = (
            f"Recent {context}, related to a slow ongoing {metric} {direction} "
            f"happening over several days, total change {change} percent."
        )
    else:
        query = (
            f"Recent {context}, related to a sudden {metric} {direction} "
            f"of {change} percent."
        )

    return query


def run_knowledge_agent(query_text: str, company_id: int = 1, top_k: int | None = None):
    """
    Main function other code calls to use the Knowledge Agent.

    query_text can come from:
    - build_query_from_anomaly() (automatic mode)
    - a question typed by the user (on-demand mode)

    V2 CHANGE: by default, we now fetch RERANK_CANDIDATE_COUNT (20)
    candidates instead of just 5. This gives the re-ranker (coming in
    the next steps) a bigger pool to work with, so it can actually
    prefer a more RECENT, slightly-less-similar ticket over an old,
    highly-similar one - which plain top-5 similarity search can't do.

    For now (until the re-ranker is wired in), we just trim down to
    FINAL_EVIDENCE_COUNT (5) using the existing similarity ranking, so
    behavior stays the same as before. The re-ranker will replace this
    trimming step directly.

    Pass an explicit top_k if you want to override the candidate count
    for a specific call (e.g. a smaller quick search).

    Returns a list of evidence pieces found (tickets, reviews, documents,
    deployment notes) along with how relevant each one is, plus their
    metadata (created_at, source_id, category) for later re-ranking.
    """
    candidate_count = top_k if top_k is not None else settings.RERANK_CANDIDATE_COUNT

    results = search(
        query=query_text,
        top_k=candidate_count,
        company_id=company_id,
    )

    evidence_list = []
    for item in results:
        evidence_list.append({
            "text": item["text"],
            "source_type": item["source_type"],
            "relevance_score": item["score"],
            # V2: carry through the new metadata fields, if present
            # (older data synced before Step 1.2 won't have these -
            # that's fine, they'll just be None)
            "created_at": item.get("created_at"),
            "source_id": item.get("source_id"),
            "category": item.get("category"),
        })

    # TEMPORARY: until the re-ranker (Steps 1.5-1.8) is wired in, we
    # just keep the top FINAL_EVIDENCE_COUNT by similarity score, same
    # as V1 behavior. This will be replaced with a call to the
    # re-ranker directly.
    evidence_list = evidence_list[:settings.FINAL_EVIDENCE_COUNT]

    return {
        "agent": "knowledge_agent",
        "query_used": query_text,
        "evidence_found": len(evidence_list),
        "evidence": evidence_list,
    }


def run_knowledge_agent_from_anomaly(anomaly: dict, company_id: int = 1, top_k: int | None = None):
    """
    Convenience function for automatic mode.
    Builds the query from the anomaly first, then searches.
    """
    query_text = build_query_from_anomaly(anomaly)
    return run_knowledge_agent(query_text, company_id=company_id, top_k=top_k)