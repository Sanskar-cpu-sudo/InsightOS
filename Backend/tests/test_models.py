"""
tests/test_models.py

Locks in the NaN-sanitization bug fix on Decision.to_dict().

Real bug this guards against: RAGAS's answer_relevancy metric can
legitimately return NaN for a degenerate answer. NaN is a valid Python
float but is NOT valid JSON (Starlette's JSONResponse explicitly
forbids it) -- a NaN score saved to a Decision row silently crashed
/dashboard, /history, and /recommendations days after the row was
written, since nothing sanitized it on the way out.
"""

from app.models import Decision


def test_to_dict_sanitizes_nan_faithfulness_score():
    decision = Decision(
        company_id=1,
        root_cause="x",
        evidence={},
        confidence=0.9,
        recommendation="y",
        faithfulness_score=float("nan"),
        relevance_score=0.5,
        outcome=None,
    )

    result = decision.to_dict()

    assert result["faithfulness_score"] is None
    assert result["relevance_score"] == 0.5


def test_to_dict_sanitizes_nan_relevance_score():
    decision = Decision(
        company_id=1,
        root_cause="x",
        evidence={},
        confidence=0.9,
        recommendation="y",
        faithfulness_score=0.7,
        relevance_score=float("nan"),
        outcome="resolved",
    )

    result = decision.to_dict()

    assert result["relevance_score"] is None
    assert result["faithfulness_score"] == 0.7


def test_to_dict_leaves_valid_scores_untouched():
    """A genuinely valid score must never be altered by the sanitization check."""
    decision = Decision(
        company_id=1,
        root_cause="x",
        evidence={},
        confidence=0.85,
        recommendation="y",
        faithfulness_score=0.72,
        relevance_score=0.61,
        outcome=None,
    )

    result = decision.to_dict()

    assert result["confidence"] == 0.85
    assert result["faithfulness_score"] == 0.72
    assert result["relevance_score"] == 0.61


def test_to_dict_leaves_none_scores_as_none():
    """A never-evaluated decision (None, not NaN) must stay None, not get coerced."""
    decision = Decision(
        company_id=1,
        root_cause="x",
        evidence={},
        confidence=0.9,
        recommendation="y",
        faithfulness_score=None,
        relevance_score=None,
        outcome=None,
    )

    result = decision.to_dict()

    assert result["faithfulness_score"] is None
    assert result["relevance_score"] is None


def test_to_dict_includes_all_expected_fields():
    """Guards against a future edit accidentally dropping a field consumers rely on."""
    decision = Decision(
        id=1,
        company_id=1,
        root_cause="root cause text",
        evidence={"topic": {"metric": "revenue"}},
        confidence=0.9,
        recommendation="recommendation text",
        faithfulness_score=0.8,
        relevance_score=0.7,
        outcome="resolved",
    )

    result = decision.to_dict()

    for field in ["id", "created_at", "root_cause", "recommendation",
                  "confidence", "faithfulness_score", "relevance_score", "outcome"]:
        assert field in result, f"to_dict() is missing expected field: {field}"

    # evidence is intentionally NOT part of the shared to_dict() -- it's
    # added separately by whichever router needs it (recommendations.py)
    assert "evidence" not in result
