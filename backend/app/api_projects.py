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
from app.db.models import (
    AuthAccount,
    FacultyProjectAssignment,
    Project,
    ProjectMember,
    Submission,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    github_url: HttpUrl | None = None


class FacultySupervisorResponse(BaseModel):
    name: str
    email: str
    department: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(BaseModel):
    id: int
    title: str
    description: str | None
    github_url: str | None
    status: str
    supervisors: list[FacultySupervisorResponse] = []

    model_config = ConfigDict(from_attributes=True)


def _get_project_supervisors(project_id: int, db: Session) -> list[FacultySupervisorResponse]:
    assignments = (
        db.query(AuthAccount)
        .join(
            FacultyProjectAssignment,
            FacultyProjectAssignment.faculty_account_id == AuthAccount.id,
        )
        .filter(
            FacultyProjectAssignment.project_id == project_id,
            AuthAccount.role == "faculty",
            AuthAccount.faculty_approved.is_(True),
        )
        .all()
    )
    return [
        FacultySupervisorResponse(
            name=acc.faculty_name or "Faculty Supervisor",
            email=acc.email,
            department=acc.department,
        )
        for acc in assignments
    ]


def _project_payload(project: Project, db: Session) -> dict:
    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "github_url": project.github_url,
        "status": project.status,
        "supervisors": _get_project_supervisors(project.id, db),
    }


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=201,
)
def create_project(
    data: ProjectCreate,
    account: Principal = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    project = Project(
        title=data.title,
        description=data.description,
        github_url=str(data.github_url) if data.github_url else None,
    )
    db.add(project)
    db.flush()
    if account.role == "faculty":
        db.add(
            FacultyProjectAssignment(
                faculty_account_id=account.id,
                project_id=project.id,
            )
        )
    elif account.role == "student" and account.student_id:
        db.add(
            ProjectMember(
                project_id=project.id,
                student_id=account.student_id,
                role="LEADER",
            )
        )
    db.commit()
    db.refresh(project)
    return _project_payload(project, db)


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
    projects = query.order_by(Project.id).all()
    return [_project_payload(project, db) for project in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    dependencies=[Depends(require_project_access)],
)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_payload(project, db)


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    dependencies=[Depends(require_project_access)],
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
    return _project_payload(project, db)


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


@router.get(
    "/{project_id}/documents",
    dependencies=[Depends(require_project_access)],
)
def list_project_documents(
    project_id: int,
    submission_id: int | None = None,
    db: Session = Depends(get_db),
    account: Principal = Depends(require_project_access),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.api_submissions import _resolve_submission_document

    query = db.query(Submission).filter_by(project_id=project_id)
    if submission_id is not None:
        query = query.filter_by(id=submission_id)
    submissions = query.order_by(Submission.week_number.desc(), Submission.id.desc()).all()

    all_docs = []
    for sub in submissions:
        for cat in ("report", "presentation", "srs"):
            doc = _resolve_submission_document(sub, cat, project, db)
            if doc is not None:
                all_docs.append(doc)

    return all_docs
