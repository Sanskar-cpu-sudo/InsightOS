"""
sync_vector_store.py

seed_data.py fills PostgreSQL with tickets, reviews, and deployment
logs. But the Knowledge Agent searches QDRANT, not Postgres directly.

This script reads everything out of Postgres and pushes it into Qdrant
as searchable text. Run this ONCE after seed_data.py (and again any
time you add new tickets/reviews/deployments to Postgres).

Run with:
    python -m app.sync_vector_store
"""

from app.database import SessionLocal, init_db
from app.models import SupportTicket, Review, DeploymentLog
from app.vector_store import init_collection, add_texts, get_qdrant_client
from app.config import get_settings

settings = get_settings()
DEFAULT_COMPANY_ID = 1


def clear_qdrant_collection():
    """
    Deletes the Qdrant collection if it already exists, so re-running
    this script gives a clean, fresh sync instead of piling duplicate
    tickets/reviews on top of old ones. Same idea as clear_existing_data()
    in seed_data.py, just for Qdrant instead of Postgres.
    """
    client = get_qdrant_client()
    existing = [c.name for c in client.get_collections().collections]
    if settings.QDRANT_COLLECTION in existing:
        client.delete_collection(settings.QDRANT_COLLECTION)


def sync_tickets(db):
    tickets = db.query(SupportTicket).filter(SupportTicket.company_id == DEFAULT_COMPANY_ID).all()
    if not tickets:
        return 0

    texts = [t.content for t in tickets]
    # V2: pass created_at (needed for recency scoring), source_id (so we
    # can trace evidence back to its Postgres row), and category
    add_texts(
        texts,
        source_type="ticket",
        company_id=DEFAULT_COMPANY_ID,
        created_at=[t.created_at.isoformat() for t in tickets],
        source_id=[t.id for t in tickets],
        category=[t.category or "general" for t in tickets],
    )
    return len(texts)


def sync_reviews(db):
    reviews = db.query(Review).filter(Review.company_id == DEFAULT_COMPANY_ID).all()
    if not reviews:
        return 0

    texts = [r.content for r in reviews]
    add_texts(
        texts,
        source_type="review",
        company_id=DEFAULT_COMPANY_ID,
        created_at=[r.created_at.isoformat() for r in reviews],
        source_id=[r.id for r in reviews],
        category=[f"{r.rating}_star" for r in reviews],
    )
    return len(texts)


def sync_deployments(db):
    deployments = db.query(DeploymentLog).filter(DeploymentLog.company_id == DEFAULT_COMPANY_ID).all()
    if not deployments:
        return 0

    texts = [d.description for d in deployments]
    add_texts(
        texts,
        source_type="deployment",
        company_id=DEFAULT_COMPANY_ID,
        created_at=[d.deployed_at.isoformat() for d in deployments],
        source_id=[d.id for d in deployments],
        category=[d.version for d in deployments],
    )
    return len(texts)


def run():
    print("Making sure database tables exist...")
    init_db()

    print("Clearing old data from Qdrant (so this sync doesn't create duplicates)...")
    clear_qdrant_collection()
    init_collection()

    db = SessionLocal()
    try:
        print("Syncing support tickets into Qdrant...")
        count = sync_tickets(db)
        print(f"  -> {count} tickets synced")

        print("Syncing reviews into Qdrant...")
        count = sync_reviews(db)
        print(f"  -> {count} reviews synced")

        print("Syncing deployment logs into Qdrant...")
        count = sync_deployments(db)
        print(f"  -> {count} deployment logs synced")

        print("Done. Qdrant is now ready for the Knowledge Agent to search.")
    finally:
        db.close()


if __name__ == "__main__":
    run()