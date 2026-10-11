from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db, require_faculty_project, require_project_access
from app.db.models import Project, ProjectMember, Student

router = APIRouter(
    prefix="/projects/{project_id}/members",
    tags=["Project Members"],
    dependencies=[Depends(require_project_access)],
)


class MemberCreate(BaseModel):
    student_id: int | None = None
    registration_number: str | None = None
    role: Literal["MEMBER"] = "MEMBER"


class MemberResponse(BaseModel):
    id: int
    project_id: int
    student_id: int
    role: str

    model_config = ConfigDict(from_attributes=True)


@router.post(
    "/",
    response_model=MemberResponse,
    status_code=201,
    dependencies=[Depends(require_project_access)],
)
def add_member(
    project_id: int,
    data: MemberCreate,
    db: Session = Depends(get_db),
):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    target_student = None
    if data.student_id is not None:
        target_student = db.get(Student, data.student_id)
    elif data.registration_number:
        clean_reg = data.registration_number.strip().upper()
        target_student = db.query(Student).filter(
            func.upper(func.trim(Student.registration_number)) == clean_reg
        ).first()

    if target_student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found. Provide a valid student ID or registration number.",
        )

    existing = db.query(ProjectMember).filter_by(
        project_id=project_id,
        student_id=target_student.id,
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Student is already a member of this project",
        )

    member = ProjectMember(
        project_id=project_id,
        student_id=target_student.id,
        role=data.role,
    )

    db.add(member)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not add project member")

    db.refresh(member)
    return member


@router.get("/", response_model=list[MemberResponse])
def list_members(project_id: int, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return (
        db.query(ProjectMember)
        .filter_by(project_id=project_id)
        .order_by(ProjectMember.id)
        .all()
    )


@router.delete(
    "/{student_id}",
    status_code=204,
    dependencies=[Depends(require_project_access)],
)
def remove_member(
    project_id: int,
    student_id: int,
    db: Session = Depends(get_db),
):
    member = db.query(ProjectMember).filter_by(
        project_id=project_id,
        student_id=student_id,
    ).first()

    if member is None:
        raise HTTPException(status_code=404, detail="Project membership not found")

    db.delete(member)
    db.commit()
