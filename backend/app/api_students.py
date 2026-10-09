from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Student

router = APIRouter(prefix="/students", tags=["Students"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    registration_number: str = Field(min_length=1, max_length=50)


class StudentResponse(BaseModel):
    id: int
    name: str
    email: str
    registration_number: str

    model_config = ConfigDict(from_attributes=True)


@router.post("/", response_model=StudentResponse, status_code=201)
def create_student(student_data: StudentCreate, db: Session = Depends(get_db)):
    existing_student = db.query(Student).filter(
        (Student.email == student_data.email)
        | (Student.registration_number == student_data.registration_number)
    ).first()

    if existing_student:
        raise HTTPException(
            status_code=409,
            detail="Email or registration number already exists",
        )

    student = Student(**student_data.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("/", response_model=list[StudentResponse])
def list_students(db: Session = Depends(get_db)):
    return db.query(Student).order_by(Student.id).all()


@router.get("/{student_id}", response_model=StudentResponse)
def get_student(student_id: int, db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.put("/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: int,
    student_data: StudentCreate,
    db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    duplicate = db.query(Student).filter(
        ((Student.email == student_data.email)
         | (Student.registration_number == student_data.registration_number)),
        Student.id != student_id,
    ).first()

    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="Email or registration number already exists",
        )

    for field, value in student_data.model_dump().items():
        setattr(student, field, value)

    db.commit()
    db.refresh(student)
    return student


@router.delete("/{student_id}", status_code=204)
def delete_student(student_id: int, db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    db.delete(student)
    db.commit()
