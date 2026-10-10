from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_roles

router = APIRouter(
    prefix="/uploads",
    tags=["Document Uploads"],
    dependencies=[Depends(require_roles("faculty"))],
)

@router.post("/", status_code=410)
def upload_document():
    raise HTTPException(
        status_code=410,
        detail="Use the project-scoped submission upload endpoint.",
    )
