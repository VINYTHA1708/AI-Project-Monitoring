from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Principal, get_db, require_roles
from app.db.models import FacultyProjectAssignment, ProjectMember, Student

router = APIRouter(
    prefix="/students",
    tags=["Students"],
    dependencies=[Depends(require_roles("faculty"))],
)


class StudentResponse(BaseModel):
    id: int
    name: str
    email: str
    registration_number: str

    model_config = ConfigDict(from_attributes=True)


@router.get("/", response_model=list[StudentResponse])
def list_students(
    account: Principal = Depends(require_roles("faculty")),
    db: Session = Depends(get_db),
):
    return (
        db.query(Student)
        .join(ProjectMember, ProjectMember.student_id == Student.id)
        .join(
            FacultyProjectAssignment,
            FacultyProjectAssignment.project_id == ProjectMember.project_id,
        )
        .filter(FacultyProjectAssignment.faculty_account_id == account.id)
        .distinct()
        .order_by(Student.id)
        .all()
    )


@router.get("/{student_id}", response_model=StudentResponse)
def get_student(
    student_id: int,
    account: Principal = Depends(require_roles("faculty")),
    db: Session = Depends(get_db),
):
    student = db.scalar(
        select(Student)
        .join(ProjectMember, ProjectMember.student_id == Student.id)
        .join(
            FacultyProjectAssignment,
            FacultyProjectAssignment.project_id == ProjectMember.project_id,
        )
        .where(
            Student.id == student_id,
            FacultyProjectAssignment.faculty_account_id == account.id,
        )
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.post("/", status_code=405)
def create_student():
    raise HTTPException(
        status_code=405,
        detail="Use verified student registration to create student accounts.",
    )


@router.put("/{student_id}", status_code=405)
def update_student(student_id: int):
    raise HTTPException(
        status_code=405,
        detail="Student identity records are not editable through the faculty API.",
    )


@router.delete("/{student_id}", status_code=405)
def delete_student(student_id: int):
    raise HTTPException(
        status_code=405,
        detail="Student records cannot be deleted through the faculty API.",
    )
