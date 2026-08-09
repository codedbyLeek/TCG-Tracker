import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.cards import router as cards_router
from app.api.collection import router as collection_router
from app.core.scheduler import register_jobs, scheduler



@asynccontextmanager

async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    register_jobs()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="TCG Tracker API",
    description="Backend API for the TCG price tracker",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(cards_router)
app.include_router(collection_router)

@app.get("/")
def root():
    return {"message": "TCG Tracker API is running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}