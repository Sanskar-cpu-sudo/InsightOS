from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import get_settings

settings = get_settings()

# Engine → Knows how to connect to the database.
# Session → Uses the engine to perform CRUD operations.

# echo=False -> set True temporarily if you want to see every SQL query printed,
# useful for debugging early on.
engine = create_engine(settings.DATABASE_URL, echo=False, future=True)

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