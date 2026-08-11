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

from app.database import init_db
from app.vector_store import init_collection

from app.routers import dashboard, upload, recommendations, history

app = FastAPI(title="InsightOS API")

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


@app.get("/")
def read_root():
    return {"message": "InsightOS API is running"}


app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
app.include_router(history.router, prefix="/history", tags=["history"])