from fastapi import FastAPI

app = FastAPI(
    title="Flow State Backend",
    description="Backend service for Flow State - capturing jam sessions and extracting musical ideas.",
    version="0.1.0",
)


@app.get("/")
def read_root():
    return {
        "name": "Flow State Backend API",
        "description": "Flow State backend service for recording jam sessions and extracting musical ideas.",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
