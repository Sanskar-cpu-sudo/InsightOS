"""
These map directly to the schema we designed:
    sales            -> read by Data Agent
    support_tickets  -> read by Knowledge Agent
    reviews          -> read by Knowledge Agent
    deployment_logs  -> read by Knowledge Agent
    decisions        -> written by Decision Agent, read by Dashboard/History
    documents        -> written by Upload route, tracks what's stored in Qdrant
"""

from sqlalchemy import Column, Integer, Float, String, Text, Date, DateTime, JSON
from sqlalchemy.sql import func

from app.database import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, nullable=False, default=1, index=True)
    date = Column(Date, nullable=False, index=True)
    revenue = Column(Float, nullable=False)
    orders = Column(Integer, nullable=False)
    avg_order_value = Column(Float, nullable=False)


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, nullable=False, default=1, index=True)
    created_at = Column(DateTime, nullable=False, index=True)
    content = Column(Text, nullable=False)
    category = Column(String, nullable=True)  # e.g. "performance", "billing"


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, nullable=False, default=1, index=True)
    created_at = Column(DateTime, nullable=False, index=True)
    content = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5


class DeploymentLog(Base):
    __tablename__ = "deployment_logs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, nullable=False, default=1, index=True)
    deployed_at = Column(DateTime, nullable=False, index=True)
    version = Column(String, nullable=False)       # e.g. "v2.1.4"
    description = Column(Text, nullable=False)      # what changed in this deploy


class Decision(Base):
    """
    This is the 'Decision Memory' table.
    One row = one recommendation the Decision Agent has ever produced.
    Nothing is ever deleted from here -> this is what powers the History page
    and lets us later evaluate 'did our past recommendations actually help'.
    """
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, nullable=False, default=1, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    root_cause = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=False)          # list of supporting facts/quotes
    confidence = Column(Float, nullable=False)        # 0.0 - 1.0
    recommendation = Column(Text, nullable=False)

    # Filled in by the Evaluation Engine right after the decision is made
    groundedness_score = Column(Float, nullable=True)
    faithfulness_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)

    # Nullable -> filled in later if/when someone marks whether it actually helped
    outcome = Column(String, nullable=True)  # e.g. "resolved", "false_positive", "ignored"


class Document(Base):
    """
    Metadata only. The actual text + vectors live in Qdrant.
    This table just tracks *what* was uploaded and *which* Qdrant point IDs
    belong to it, so we can (if needed) delete/update a document later.
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, nullable=False, default=1, index=True)
    filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime, server_default=func.now())
    qdrant_point_ids = Column(JSON, nullable=False)  # list of point IDs in Qdrant