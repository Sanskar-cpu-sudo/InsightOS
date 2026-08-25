"""
tests/test_reranker.py

Proves the weighted blend actually changes ranking outcomes -- not
just that the functions run without crashing. The real thing this
protects: an old-but-textually-similar ticket should NOT automatically
beat a newer, more relevant one just because it shares more keywords.
"""

from datetime import datetime, timedelta, UTC

from app.reranker import recency_score, reliability_score, final_score, rerank_evidence


def test_recency_score_decays_with_age():
    now = datetime.now(UTC).isoformat()
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    assert recency_score(now) > recency_score(old)


def test_recency_score_handles_missing_timestamp():
    assert recency_score(None) == 0.5  # neutral default, not a crash


def test_reliability_score_ranks_deployment_above_review():
    """Deployment logs are internal fact records; reviews are the noisiest signal."""
    assert reliability_score("deployment") > reliability_score("review")


def test_reliability_score_handles_unknown_source_type():
    assert reliability_score("something_new") == 0.5  # neutral default, not a crash


def test_recent_evidence_can_outrank_older_more_similar_evidence():
    """
    The core claim of Phase 1: a recent, reliable piece of evidence
    with LOWER text similarity should be able to beat an old piece of
    evidence with HIGHER text similarity.
    """
    now = datetime.now(UTC)
    old = (now - timedelta(days=30)).isoformat()
    fresh = now.isoformat()

    old_but_similar = {"relevance_score": 0.95, "created_at": old, "source_type": "review"}
    new_but_less_similar = {"relevance_score": 0.55, "created_at": fresh, "source_type": "deployment"}

    assert final_score(new_but_less_similar) > final_score(old_but_similar)


def test_rerank_evidence_sorts_and_trims_to_top_k():
    now = datetime.now(UTC).isoformat()
    pool = [
        {"text": "low", "relevance_score": 0.3, "created_at": now, "source_type": "ticket"},
        {"text": "high", "relevance_score": 0.9, "created_at": now, "source_type": "ticket"},
        {"text": "mid", "relevance_score": 0.6, "created_at": now, "source_type": "ticket"},
    ]

    result = rerank_evidence(pool, top_k=2)

    assert len(result) == 2
    assert result[0]["text"] == "high"
    assert result[1]["text"] == "mid"
    assert "final_score" in result[0]


def test_rerank_evidence_handles_empty_pool():
    assert rerank_evidence([]) == []


def test_rerank_evidence_does_not_mutate_original_dicts():
    """rerank_evidence should return copies, not attach final_score to the caller's originals."""
    now = datetime.now(UTC).isoformat()
    original = {"text": "x", "relevance_score": 0.5, "created_at": now, "source_type": "ticket"}
    pool = [original]

    rerank_evidence(pool)

    assert "final_score" not in original
