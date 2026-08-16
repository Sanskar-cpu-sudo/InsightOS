"""
main.py

This is the entry point of the whole backend. It:
1. Creates the FastAPI app
2. Sets up the database and vector store on startup
3. Connects all the routers (the different groups of API endpoints)

To run this locally:
    uvicorn app.main:app --reload
""" 

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logfire

from app.database import init_db
from app.vector_store import init_collection
from app.scheduler import start_scheduler, stop_scheduler
from app.monitoring import configure_monitoring

from app.routers import dashboard, upload, recommendations, history, reports

# V2, Step 6.2: connect to Logfire (idempotent, see monitoring.py) --
# database.py already calls this too, whichever module happens to
# import first sets it up, the other just finds it already configured.
configure_monitoring()

app = FastAPI(title="InsightOS API")

# V2, Step 6.2: every HTTP request now shows up in Logfire too (which
# route, status code, how long it took), not just LLM calls and DB
# queries. Purely observability -- doesn't change how any route behaves.
logfire.instrument_fastapi(app)

# Allows the React frontend (running on a different port) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for a real product you would list exact domains here
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """
    Runs once when the server starts.
    Makes sure the database tables and the Qdrant collection exist
    before any requests come in.
    """
    init_db()
    init_collection()

    # V2, Step 5.2: start the real scheduler so the automatic pipeline
    # (Data Agent -> Knowledge Agent -> Decision Agent) now runs on its
    # own, on a recurring interval (see scheduler.py), instead of only
    # ever running when someone manually calls POST /recommendations/run-now.
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    """
    Runs once when the server stops.
    V2, Step 5.2: shuts the scheduler down cleanly, so no background
    job is left half-running (or still holding a db session open)
    after the app itself has already stopped.
    """
    stop_scheduler()


@app.get("/")
def read_root():
    return {"message": "InsightOS API is running"}


app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
app.include_router(history.router, prefix="/history", tags=["history"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])