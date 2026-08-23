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

from datetime import date, datetime, timedelta, UTC

from sqlalchemy.orm import Session

from app.vector_store import search 
from app.config import get_settings
from app.reranker import rerank_evidence
from app.models import DeploymentLog

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


def build_query_from_incident(incident: dict) -> str:
    """
    V2, Step 3.3: same idea as build_query_from_anomaly() above, but for
    a whole INCIDENT (see data_agent.py's build_incident(), Step 3.2) --
    several metrics moving together, not just one.

    Searching with only "revenue" context when revenue AND orders
    crashed together misses half the picture: orders' own context list
    (cart abandonment, shipping delays, product availability, ...) might
    be exactly what surfaces the right ticket. So this pulls in and
    combines METRIC_CONTEXT for EVERY metric involved in the incident,
    not just one, then folds in each metric's own percent change so the
    query still says what actually happened, not just what kind of
    thing to look for.

    Example output:
        "Recent customer complaints about checkout, payment failures,
        cart abandonment, shipping delays, ..., related to a checkout
        performance incident where multiple metrics moved together:
        revenue down 59.6 percent, orders down 59.5 percent."
    """
    metrics = incident.get("metrics", [])
    label = incident.get("incident", "business metric")

    # Gather each metric's own context phrases, preserving metric order,
    # but skip a phrase we've already added -- METRIC_CONTEXT entries
    # overlap on purpose (e.g. "checkout problems" appears for both
    # revenue and orders), and repeating it doesn't add anything, it
    # just makes the query longer and less focused.
    seen_phrases = set()
    combined_context_parts = []
    for metric in metrics:
        for phrase in METRIC_CONTEXT.get(metric, "").split(", "):
            phrase = phrase.strip()
            if phrase and phrase not in seen_phrases:
                seen_phrases.add(phrase)
                combined_context_parts.append(phrase)
    combined_context = ", ".join(combined_context_parts)

    # summarize each metric's own change, e.g.
    # "revenue down 59.6 percent, orders down 59.5 percent"
    change_summaries = []
    for anomaly in incident.get("anomalies", []):
        metric_name = anomaly.get("metric", "a metric")
        change = anomaly.get("percent_change", anomaly.get("total_percent_change", ""))
        direction = "down" if str(change).startswith("-") else "up"
        change_summaries.append(f"{metric_name} {direction} {str(change).lstrip('-')} percent")
    change_text = ", ".join(change_summaries)

    return (
        f"Recent {combined_context}, related to a {label.replace('_', ' ')} incident "
        f"where multiple metrics moved together: {change_text}."
    )


def _to_utc_datetime(value) -> datetime:
    """
    Normalizes a date, datetime, or ISO-format string into a
    timezone-aware UTC datetime, so comparisons below are always
    apples-to-apples regardless of which shape the caller passed in.

    (Same defensive spirit as recency_score()'s timestamp handling in
    reranker.py -- anomalies can hand us a bare date, DeploymentLog
    rows can come back tz-naive from Postgres.)
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value)

    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value


def find_recent_deployment(
    db: Session,
    anomaly_time,
    company_id: int = 1,
    hours: int = 48,
) -> dict | None:
    """
    Phase 2, Step 2.1: a TARGETED lookup, not a semantic search.

    Semantic search (run_knowledge_agent below) finds evidence that
    reads as RELATED in meaning. This function instead asks a much more
    specific, structural question directly against Postgres: "did a
    deployment actually happen shortly before this anomaly?" That's a
    fact we can look up directly -- there's no need to embed anything
    or guess at wording, so we skip Qdrant entirely here.

    anomaly_time: when the anomaly was observed. Accepts a date,
    datetime, or ISO string (e.g. the "date" field on a point_anomaly
    dict, or just date.today() for a trend_anomaly, which has no
    single date of its own).

    hours: how far back before anomaly_time counts as "recent" (default
    48h, per the plan). A deployment is only a plausible cause if it
    happened BEFORE the anomaly, so we never look forward in time.

    Returns a dict describing the closest deployment in that window
    (None if no deployment happened in that window at all). If more
    than one deployment happened in the window, we return the most
    RECENT one -- the one closest to the anomaly is the most plausible
    single cause.
    """
    anomaly_dt = _to_utc_datetime(anomaly_time)
    window_start = anomaly_dt - timedelta(hours=hours)

    deployments = (
        db.query(DeploymentLog)
        .filter(DeploymentLog.company_id == company_id)
        .filter(DeploymentLog.deployed_at >= window_start)
        .filter(DeploymentLog.deployed_at <= anomaly_dt)
        .order_by(DeploymentLog.deployed_at.desc())
        .all()
    )

    if not deployments:
        return None

    closest = deployments[0]
    closest_dt = _to_utc_datetime(closest.deployed_at)
    hours_before_anomaly = (anomaly_dt - closest_dt).total_seconds() / 3600

    return {
        "id": closest.id,
        "version": closest.version,
        "description": closest.description,
        "deployed_at": closest.deployed_at.isoformat()
        if hasattr(closest.deployed_at, "isoformat")
        else str(closest.deployed_at),
        "hours_before_anomaly": round(hours_before_anomaly, 1),
    }


def deployment_as_evidence(deployment: dict) -> dict:
    """
    Phase 2, Step 2.2: converts the dict find_recent_deployment() returns
    into the same evidence shape run_knowledge_agent() produces, so the
    two can be merged into one evidence list -- that merging itself
    happens in graph.py (Step 2.3), not here.

    The key thing this step adds: "evidence_role": "temporal_signal",
    instead of the "semantic_match" every Qdrant-found result gets (see
    search()/run_knowledge_agent() above). That's the whole point of
    Step 2.2 -- "a deployment provably happened N hours before this
    anomaly" is a fundamentally different, stronger kind of signal than
    "this ticket's wording happens to be similar", and the Decision
    Agent (Step 2.4) and later the evidence-safety guardrails (Phase 4)
    both need to be able to tell the two apart instead of the evidence
    list treating everything as equally-weighted "similar stuff we found".

    Unlike semantic-match evidence, this has no relevance_score/
    final_score -- it wasn't ranked by similarity, so there's nothing to
    put there. Its strength comes from being a concrete, checkable fact,
    not a similarity score.
    """
    text = (
        f"Deployment {deployment['version']} ({deployment['description']}) "
        f"went out {deployment['hours_before_anomaly']} hours before this anomaly."
    )

    return {
        "text": text,
        "source_type": "deployment",
        "evidence_role": "temporal_signal",
        "created_at": deployment["deployed_at"],
        "source_id": deployment["id"],
        "category": deployment.get("version"),
    }


def run_knowledge_agent(query_text: str, company_id: int = 1, top_k: int | None = None):
    """
    Main function other code calls to use the Knowledge Agent.

    query_text can come from:
    - build_query_from_anomaly() (automatic mode)
    - a question typed by the user (on-demand mode)

    V2 CHANGE: by default, we now fetch RERANK_CANDIDATE_COUNT (20)
    candidates instead of just 5. This gives the re-ranker a bigger pool
    to work with, so it can prefer a more RECENT, slightly-less-similar
    ticket over an old, highly-similar one - which plain top-5 similarity
    search can't do. The pool is then passed through rerank_evidence()
    (see reranker.py), which combines similarity + recency + reliability
    into a single final_score and trims it down to FINAL_EVIDENCE_COUNT.

    Pass an explicit top_k if you want to override the candidate count
    for a specific call (e.g. a smaller quick search).

    Returns a list of evidence pieces found (tickets, reviews, documents,
    deployment notes) along with their relevance_score, final_score, and
    metadata (created_at, source_id, category).
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
            # V2 Step 2.2: everything here comes from semantic search,
            # so this is "semantic_match" unless something upstream
            # explicitly overrode it. Deployment evidence found via
            # find_recent_deployment() instead gets "temporal_signal" --
            # see deployment_as_evidence() below.
            "evidence_role": item.get("evidence_role", "semantic_match"),
            # V2: carry through the new metadata fields, if present
            # (older data synced before Step 1.2 won't have these -
            # that's fine, they'll just be None)
            "created_at": item.get("created_at"),
            "source_id": item.get("source_id"),
            "category": item.get("category"),
        })

    # V2: re-rank the full candidate pool by similarity + recency +
    # reliability (Steps 1.5-1.8), instead of just keeping the top
    # FINAL_EVIDENCE_COUNT by raw similarity like V1 did. This is what
    # lets a recent, highly-relevant ticket beat an old one that merely
    # happens to use similar words. rerank_evidence() also attaches a
    # "final_score" to each surviving item, and already trims down to
    # settings.FINAL_EVIDENCE_COUNT for us.
    evidence_list = rerank_evidence(evidence_list)

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


def run_knowledge_agent_from_incident(incident: dict, company_id: int = 1, top_k: int | None = None):
    """
    V2, Step 3.3: convenience function for automatic mode when the
    anomalies found are CORRELATED (data_agent.py's build_incident() is
    not None). Same pattern as run_knowledge_agent_from_anomaly() above,
    just using the incident-aware query builder so the search covers
    every metric involved, not only one.
    """
    query_text = build_query_from_incident(incident)
    return run_knowledge_agent(query_text, company_id=company_id, top_k=top_k)