"""
tests/conftest.py

Shared pytest fixtures + test environment setup.

Stubs ONLY the two things that genuinely can't run in a normal test
environment without extra infrastructure:
  - qdrant_client       (needs a real Qdrant server)
  - sentence_transformers (needs to download a real embedding model)

Everything else -- nemoguardrails, langchain_groq, litellm, ragas -- is
the REAL package. Individual tests mock the actual network call (e.g.
ChatGroq.ainvoke, litellm.completion) rather than stubbing the whole
library, so we're testing our actual integration code against each
library's real behavior, not a hand-rolled fake of it. This is the
exact same approach that found every real bug during manual testing --
codifying it into the test suite instead of one-off scripts.
"""

import os
import sys
import types

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")
# forces the same nemoguardrails LLM-framework fix guardrails.py's own
# module-level os.environ.setdefault() already applies -- setting it
# here too means it's correct even if guardrails.py's own module-level
# line hasn't executed yet by the time another module imports first
os.environ.setdefault("NEMOGUARDRAILS_LLM_FRAMEWORK", "langchain")


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


_stub("qdrant_client", QdrantClient=object)
_qdrant_models = _stub("qdrant_client.models")
for _name in ["Distance", "VectorParams", "PointStruct", "Filter", "FieldCondition", "MatchValue"]:
    setattr(_qdrant_models, _name, object)

_stub("sentence_transformers", SentenceTransformer=object)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base


@pytest.fixture()
def db():
    """A fresh, isolated in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
