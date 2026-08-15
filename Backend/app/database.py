from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import logfire

from app.config import get_settings
from app.monitoring import configure_monitoring

settings = get_settings()

# V2, Step 6.2: connect to Logfire (if not already connected -- this is
# idempotent, see monitoring.py) before instrumenting the engine below,
# so there's actually somewhere for the instrumentation to send to.
configure_monitoring()

# Engine → Knows how to connect to the database.
# Session → Uses the engine to perform CRUD operations.

# echo=False -> set True temporarily if you want to see every SQL query printed,
# useful for debugging early on.
engine = create_engine(settings.DATABASE_URL, echo=False, future=True)

# V2, Step 6.2: every query that runs through this engine now shows up
# in Logfire too (which query, how long it took), not just LLM calls.
# This is purely observability -- it doesn't change how the engine
# behaves, wraps it, or intercepts anything the app relies on.
logfire.instrument_sqlalchemy(engine=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency. Usage in a route:

        @router.get("/something")
        def some_route(db: Session = Depends(get_db)):
            ...

    This guarantees the DB session is always closed after the request,
    even if the route raises an exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import app.models  # noqa: F401  (ensures models are registered on Base before create_all)
    Base.metadata.create_all(bind=engine)