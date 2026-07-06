from fastapi import FastAPI

app = FastAPI(
    title="TCG Tracker API",
    description="Backend API for the TCG price tracker",
    version="0.1.0",
)


@app.get("/")
def root():
    return {"message": "TCG Tracker API is running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}