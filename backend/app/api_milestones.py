from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import require_faculty_project, require_project_access, get_db
from app.db.models import Milestone, Project

router = APIRouter(
    prefix="/projects/{project_id}/milestones",
    tags=["Milestones"],
    dependencies=[Depends(require_project_access)],
)


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    due_date: date | None = None


class MilestoneUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    due_date: date | None = None
    completed: bool = False


class MilestoneResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: str | None
    due_date: date | None
    status: str
    completed: bool

    model_config = ConfigDict(from_attributes=True)


def ensure_project_exists(project_id: int, db: Session):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post(
    "/",
    response_model=MilestoneResponse,
    status_code=201,
    dependencies=[Depends(require_faculty_project)],
)
def create_milestone(
    project_id: int,
    data: MilestoneCreate,
    db: Session = Depends(get_db),
):
    ensure_project_exists(project_id, db)

    milestone = Milestone(
        project_id=project_id,
        title=data.title,
        description=data.description,
        due_date=data.due_date,
        status="PENDING",
        completed=False,
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


@router.get("/", response_model=list[MilestoneResponse])
def list_milestones(project_id: int, db: Session = Depends(get_db)):
    ensure_project_exists(project_id, db)
    return (
        db.query(Milestone)
        .filter(Milestone.project_id == project_id)
        .order_by(Milestone.id)
        .all()
    )


@router.get("/{milestone_id}", response_model=MilestoneResponse)
def get_milestone(
    project_id: int,
    milestone_id: int,
    db: Session = Depends(get_db),
):
    ensure_project_exists(project_id, db)
    milestone = db.query(Milestone).filter(
        Milestone.id == milestone_id,
        Milestone.project_id == project_id,
    ).first()

    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return milestone


@router.put(
    "/{milestone_id}",
    response_model=MilestoneResponse,
    dependencies=[Depends(require_faculty_project)],
)
def update_milestone(
    project_id: int,
    milestone_id: int,
    data: MilestoneUpdate,
    db: Session = Depends(get_db),
):
    ensure_project_exists(project_id, db)
    milestone = db.query(Milestone).filter(
        Milestone.id == milestone_id,
        Milestone.project_id == project_id,
    ).first()

    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")

    milestone.title = data.title
    milestone.description = data.description
    milestone.due_date = data.due_date
    milestone.completed = data.completed
    milestone.status = "COMPLETED" if data.completed else "PENDING"

    db.commit()
    db.refresh(milestone)
    return milestone


@router.delete(
    "/{milestone_id}",
    status_code=204,
    dependencies=[Depends(require_faculty_project)],
)
def delete_milestone(
    project_id: int,
    milestone_id: int,
    db: Session = Depends(get_db),
):
    ensure_project_exists(project_id, db)
    milestone = db.query(Milestone).filter(
        Milestone.id == milestone_id,
        Milestone.project_id == project_id,
    ).first()

    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")

    db.delete(milestone)
    db.commit()
