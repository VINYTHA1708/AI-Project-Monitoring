from fastapi import FastAPI

from app.db.database import engine
from app.api_students import router as students_router
from app.api_projects import router as projects_router
from app.api_milestones import router as milestones_router
from app.api_members import router as members_router
from app.api_submissions import router as submissions_router
from app.api_progress import router as progress_router
from app.api_uploads import router as uploads_router
from app.api_submission_uploads import router as submission_uploads_router

app = FastAPI(
    title="AI-Based Student Project Monitoring & Review Automation System",
    description="Backend API for monitoring student projects, milestones, and submissions.",
    version="1.0.0",
)

app.include_router(students_router)
app.include_router(projects_router)
app.include_router(milestones_router)
app.include_router(members_router)
app.include_router(submissions_router)
app.include_router(progress_router)
app.include_router(uploads_router)
app.include_router(submission_uploads_router)


@app.get("/")
def root():
    return {
        "message": "AI Project Monitoring API is running",
        "status": "success",
    }


@app.get("/health")
def health_check():
    try:
        with engine.connect():
            return {"status": "healthy", "database": "connected"}
    except Exception:
        return {"status": "unhealthy", "database": "disconnected"}
