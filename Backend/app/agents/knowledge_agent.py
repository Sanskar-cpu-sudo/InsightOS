from app.vector_store import search


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


def run_knowledge_agent(query_text: str, company_id: int = 1, top_k: int = 5):
    """
    Main function other code calls to use the Knowledge Agent.

    query_text can come from:
    - build_query_from_anomaly() (automatic mode)
    - a question typed by the user (on-demand mode)

    Returns a list of evidence pieces found (tickets, reviews, documents,
    deployment notes) along with how relevant each one is.
    """
    results = search(
        query=query_text,
        top_k=top_k,
        company_id=company_id,
    )

    evidence_list = []
    for item in results:
        evidence_list.append({
            "text": item["text"],
            "source_type": item["source_type"],
            "relevance_score": item["score"],
        })

    return {
        "agent": "knowledge_agent",
        "query_used": query_text,
        "evidence_found": len(evidence_list),
        "evidence": evidence_list,
    }


def run_knowledge_agent_from_anomaly(anomaly: dict, company_id: int = 1, top_k: int = 5):
    """
    Convenience function for automatic mode.
    Builds the query from the anomaly first, then searches.
    """
    query_text = build_query_from_anomaly(anomaly)
    return run_knowledge_agent(query_text, company_id=company_id, top_k=top_k)