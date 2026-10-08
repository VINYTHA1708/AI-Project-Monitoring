from fastapi import FastAPI

app = FastAPI(
    title="AI-Based Student Project Monitoring & Review Automation System",
    version="1.0.0",
)


@app.get("/")
def root():
    return {
        "message": "AI Project Monitoring System API is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }