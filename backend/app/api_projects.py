from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    Principal,
    get_current_account,
    get_db,
    require_faculty_project,
    require_project_access,
    require_roles,
)
from app.db.models import FacultyProjectAssignment, Project, ProjectMember

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    github_url: HttpUrl | None = None


class ProjectResponse(BaseModel):
    id: int
    title: str
    description: str | None
    github_url: str | None
    status: str

    model_config = ConfigDict(from_attributes=True)


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=201,
    dependencies=[Depends(require_roles("faculty"))],
)
def create_project(
    data: ProjectCreate,
    account: Principal = Depends(require_roles("faculty")),
    db: Session = Depends(get_db),
):
    project = Project(
        title=data.title,
        description=data.description,
        github_url=str(data.github_url) if data.github_url else None,
    )
    db.add(project)
    db.flush()
    db.add(
        FacultyProjectAssignment(
            faculty_account_id=account.id,
            project_id=project.id,
        )
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/", response_model=list[ProjectResponse])
def list_projects(
    account: Principal = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    if account.role == "faculty":
        query = (
            db.query(Project)
            .join(
                FacultyProjectAssignment,
                FacultyProjectAssignment.project_id == Project.id,
            )
            .filter(FacultyProjectAssignment.faculty_account_id == account.id)
        )
    else:
        query = (
            db.query(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(ProjectMember.student_id == account.student_id)
        )
    return query.order_by(Project.id).all()


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    dependencies=[Depends(require_project_access)],
)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    dependencies=[Depends(require_faculty_project)],
)
def update_project(
    project_id: int,
    data: ProjectCreate,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project.title = data.title
    project.description = data.description
    project.github_url = str(data.github_url) if data.github_url else None

    db.commit()
    db.refresh(project)
    return project


@router.delete(
    "/{project_id}",
    status_code=204,
    dependencies=[Depends(require_faculty_project)],
)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()
