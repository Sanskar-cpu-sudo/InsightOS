"""
vector_store.py
----------------
Wraps Qdrant so the rest of the app never talks to Qdrant directly --
it just calls simple functions like `search()` and `add_texts()`.

Two jobs happen here:
  1. Turn text into vectors (embedding), using Sentence Transformers.
  2. Store/search those vectors in Qdrant.

WHAT GETS STORED HERE (from multiple sources, all in one collection):
  - Uploaded PDF/document chunks   (source_type="document")
  - Support tickets                (source_type="ticket")
  - Reviews                        (source_type="review")
  - Deployment log descriptions    (source_type="deployment")

Storing all of these together (instead of separate collections) lets the
Knowledge Agent run ONE semantic search and get back a mix of whatever's
most relevant -- a ticket, a review, AND a deployment note -- which is
exactly the cross-source evidence gathering the Decision Agent needs.
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from sentence_transformers import SentenceTransformer

from app.config import get_settings

settings = get_settings()

# --- Singletons -------------------------------------------------------
# We only want ONE embedding model loaded in memory (it's ~80MB+ and slow
# to load) and ONE Qdrant client connection, reused everywhere.

_embedding_model: SentenceTransformer | None = None
_qdrant_client: QdrantClient | None = None

# all-MiniLM-L6-v2 produces 384-dimensional vectors. If you ever change
# EMBEDDING_MODEL in config.py to a different model, this number must
# match that model's output size, or Qdrant will reject inserts.
VECTOR_SIZE = 384


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedding_model


def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    return _qdrant_client


def init_collection():
    """
    Creates the Qdrant collection if it doesn't already exist.
    Safe to call every time the app starts -- it checks first.
    """
    client = get_qdrant_client()
    existing = [c.name for c in client.get_collections().collections]

    if settings.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def embed(texts: list[str]) -> list[list[float]]:
    """Converts a list of text strings into a list of embedding vectors."""
    model = get_embedding_model()
    vectors = model.encode(texts, convert_to_numpy=True)
    return vectors.tolist()


def add_texts(
    texts: list[str],
    source_type: str,          # "document" | "ticket" | "review" | "deployment"
    company_id: int = 1,
    created_at: list[str] | None = None,   # ISO format timestamps, one per text
    source_id: list[int] | None = None,    # the Postgres row id each text came from
    category: list[str] | None = None,     # e.g. "performance", "billing" (optional)
    evidence_role: str = "semantic_match", # V2 Step 2.2: how the Decision Agent
                                            # should weigh this evidence; see search()
    extra_payload: list[dict] | None = None,
) -> list[str]:
    """
    Embeds and stores a batch of texts in Qdrant.

    V2 CHANGE: we now explicitly store created_at, source_id, and
    category as their own fields (not just buried in extra_payload).
    This is needed for Phase 1's re-ranker, which has to know HOW OLD
    each piece of evidence is (created_at) and needs a way to trace
    evidence back to its original Postgres row (source_id).

    created_at / source_id / category are all OPTIONAL lists - if you
    don't have this info for a particular call, just leave them out
    and those fields simply won't be set on those points.

    evidence_role (V2, Step 2.2): tags how the Decision Agent should
    weigh this evidence. Everything synced through here defaults to
    "semantic_match" -- it was found by similarity search. The other
    role, "temporal_signal", is only ever attached at query time (in
    knowledge_agent.py's deployment_as_evidence()), not stored in
    Qdrant, since it depends on which anomaly is being investigated.

    `extra_payload` still works too, for anything else you want to
    attach that doesn't have its own dedicated field.

    Returns the list of Qdrant point IDs that were created -- callers
    (like the upload route) save these IDs in Postgres so they can
    delete/update this data later if needed.
    """
    import uuid

    if not texts:
        return []

    vectors = embed(texts)
    point_ids = [str(uuid.uuid4()) for _ in texts]

    points = []
    for i, (text, vector, point_id) in enumerate(zip(texts, vectors, point_ids)):
        payload = {
            "text": text,
            "source_type": source_type,
            "company_id": company_id,
            "evidence_role": evidence_role,
        }

        if created_at:
            payload["created_at"] = created_at[i]
        if source_id:
            payload["source_id"] = source_id[i]
        if category:
            payload["category"] = category[i]

        if extra_payload:
            payload.update(extra_payload[i])

        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

    client = get_qdrant_client()
    client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)

    return point_ids


def search(
    query: str,
    top_k: int = 5,
    company_id: int = 1,
    source_types: list[str] | None = None,
) -> list[dict]:
    """
    Semantic search: finds the `top_k` stored texts most similar in
    MEANING to `query` (not exact keyword match).

    `source_types` optionally restricts results to certain kinds of
    evidence, e.g. search(..., source_types=["ticket", "review"])
    to skip documents/deployments for a particular question.

    Returns a list of dicts: [{"text": ..., "source_type": ..., "score": ..., ...}]
    `score` is a similarity score between 0 and 1 (higher = more relevant).
    """
    query_vector = embed([query])[0]

    must_conditions = [
        FieldCondition(key="company_id", match=MatchValue(value=company_id))
    ]
    if source_types:
        # Qdrant needs an OR across allowed source_types; simplest way
        # for a small fixed list is to run one filtered search per type
        # and merge -- but for V1 simplicity we filter client-side instead
        # if more than one type is requested.
        pass

    query_filter = Filter(must=must_conditions)

    client = get_qdrant_client()
    results = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k * 3 if source_types else top_k,  # over-fetch if we'll filter client-side
    ).points

    output = []
    for r in results:
        payload = r.payload or {}
        if source_types and payload.get("source_type") not in source_types:
            continue
        output.append({
            "text": payload.get("text"),
            "source_type": payload.get("source_type"),
            "score": round(r.score, 4),
            # V2 Step 2.2: everything found by THIS function (semantic
            # search) is tagged "semantic_match". Deployment evidence
            # found via the targeted find_recent_deployment() lookup in
            # knowledge_agent.py is tagged "temporal_signal" instead --
            # that distinction is what lets the Decision Agent treat a
            # provable "a deploy happened N hours ago" fact differently
            # from "this ticket's wording happens to be similar".
            # Default here covers points synced before this field
            # existed, so old data doesn't come back with a missing key.
            "evidence_role": payload.get("evidence_role", "semantic_match"),
            **{k: v for k, v in payload.items() if k not in ("text", "source_type", "company_id", "evidence_role")},
        })
        if len(output) >= top_k:
            break

    return output