from fastapi import FastAPI

from app.api.cards import router as cards_router
from app.api.collection import router as collection_router

app = FastAPI(
    title="TCG Tracker API",
    description="Backend API for the TCG price tracker",
    version="0.1.0",
)

app.include_router(cards_router)
app.include_router(collection_router)

@app.get("/")
def root():
    return {"message": "TCG Tracker API is running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}