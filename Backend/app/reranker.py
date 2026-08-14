"""
reranker.py

V1's Knowledge Agent only looked at semantic similarity. The problem:
an old ticket that happens to use very similar words can outrank a
brand new ticket that's actually more relevant right now.

This file fixes that by re-scoring evidence using THREE things
combined, not just similarity:

    final_score = 0.60 * similarity + 0.25 * recency + 0.15 * reliability

We build this piece by piece:
  1.5 - recency score      (done)
  1.6 - reliability score  (done)
  1.7 - combine into final_score   (done)
  1.8 - return the top few after re-ranking   (done, this step)
"""

from datetime import datetime, UTC

from app.config import get_settings

settings = get_settings()


def recency_score(created_at_str: str | None) -> float:
    """
    Turns "how old is this piece of evidence" into a score from 0 to 1.
    1.0 = brand new, closer to 0 = older.

    We use a "half-life" decay - same idea as radioactive decay, just
    applied to relevance instead of atoms. Every RECENCY_HALF_LIFE_DAYS
    that pass, the score cuts in half.

    Example with a 7 day half-life:
        0 days old  -> 1.00
        7 days old  -> 0.50
        14 days old -> 0.25
        21 days old -> 0.125

    If created_at is missing (older data that doesn't have it yet), we
    return a neutral 0.5 instead of crashing or unfairly punishing it.
    """
    if not created_at_str:
        return 0.5

    try:
        created_at = datetime.fromisoformat(created_at_str)
        # if the stored timestamp has no timezone info, treat it as UTC
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        # if the timestamp is malformed for any reason, don't crash the
        # whole pipeline over it - just treat it as neutral
        return 0.5

    now = datetime.now(UTC)
    age_in_days = (now - created_at).total_seconds() / 86400

    if age_in_days < 0:
        # a timestamp in the future shouldn't happen, but if it does,
        # just treat it as maximally recent instead of erroring
        age_in_days = 0

    half_life = settings.RECENCY_HALF_LIFE_DAYS
    score = 0.5 ** (age_in_days / half_life)

    return round(score, 4)


# Fixed reliability weight per source_type, 0 to 1. Higher = more trustworthy
# as a signal on its own, independent of how similar or recent it is.
#
# Reasoning:
#   deployment - an internal operational record of what we actually shipped
#                and when. Not an opinion, it's a fact. Most reliable.
#   document   - an uploaded policy/report document. Curated, intentional
#                writing, but still just one document's point of view.
#   ticket     - a real customer describing a real problem, but it's one
#                person's account and can be misdiagnosed by them.
#   review     - public reviews are useful signal but the noisiest: mixed
#                motives, venting, unrelated complaints bundled together.
SOURCE_RELIABILITY_WEIGHTS = {
    "deployment": 1.0,
    "document": 0.9,
    "ticket": 0.7,
    "review": 0.6,
}

# Anything not in the map above (or missing entirely) falls back to this
# neutral score, same approach as recency_score()'s handling of missing data.
DEFAULT_RELIABILITY_SCORE = 0.5


def reliability_score(source_type: str | None) -> float:
    """
    Turns "what kind of source is this" into a score from 0 to 1, using
    the fixed weights in SOURCE_RELIABILITY_WEIGHTS above.

    Unlike recency_score(), this doesn't decay or compute anything -- it's
    a straight lookup. It exists as its own function (rather than being
    inlined into the final-score combination in Step 1.7) so it's easy to
    unit test on its own and easy to tune the weights later without
    touching the combination logic.

    If source_type is missing or not one of the known types, we return a
    neutral default rather than crashing or unfairly punishing it.
    """
    if not source_type:
        return DEFAULT_RELIABILITY_SCORE

    return SOURCE_RELIABILITY_WEIGHTS.get(source_type, DEFAULT_RELIABILITY_SCORE)


def final_score(evidence_item: dict) -> float:
    """
    Combines similarity + recency + reliability into ONE score per piece
    of evidence, using the weights from config.py:

        final_score = SIMILARITY_WEIGHT  * similarity
                     + RECENCY_WEIGHT     * recency
                     + RELIABILITY_WEIGHT * reliability

    Why a weighted blend instead of just re-sorting by recency: a very
    old but extremely relevant piece of evidence should still be able to
    beat a brand new but only loosely related one. Recency and
    reliability nudge the ranking, they don't override similarity.

    evidence_item is one dict from the Knowledge Agent's evidence list,
    expected to have "relevance_score" (similarity, 0-1 from Qdrant),
    "created_at", and "source_type" -- exactly the shape
    run_knowledge_agent() already builds in knowledge_agent.py.

    Returns a single float, 0 to 1 (assuming the three weights sum to 1
    and similarity/recency/reliability are each already 0-1).
    """
    similarity = evidence_item.get("relevance_score") or 0.0
    recency = recency_score(evidence_item.get("created_at"))
    reliability = reliability_score(evidence_item.get("source_type"))

    score = (
        settings.SIMILARITY_WEIGHT * similarity
        + settings.RECENCY_WEIGHT * recency
        + settings.RELIABILITY_WEIGHT * reliability
    )

    return round(score, 4)


def rerank_evidence(evidence_list: list[dict], top_k: int | None = None) -> list[dict]:
    """
    Takes the full pool of candidate evidence (e.g. the 20 fetched by
    the Knowledge Agent's over-fetch in Step 1.4), scores each one with
    final_score(), sorts best-first, and keeps only the top `top_k`.

    This is what the Knowledge Agent should call INSTEAD OF its old
    "just keep the top N by similarity" trimming step -- that was only
    ever a placeholder until this function existed (see the TEMPORARY
    comment in knowledge_agent.py).

    Each returned evidence dict gets a new "final_score" field attached,
    so the score used for ranking is visible for logging/debugging and
    for showing in the UI later, the same way relevance_score already is.

    top_k defaults to settings.FINAL_EVIDENCE_COUNT if not given, so
    callers don't need to know that number themselves.
    """
    if not evidence_list:
        return []

    keep_count = top_k if top_k is not None else settings.FINAL_EVIDENCE_COUNT

    scored = []
    for item in evidence_list:
        # don't mutate the caller's original dicts -- copy first
        item_with_score = dict(item)
        item_with_score["final_score"] = final_score(item)
        scored.append(item_with_score)

    scored.sort(key=lambda item: item["final_score"], reverse=True)

    return scored[:keep_count]