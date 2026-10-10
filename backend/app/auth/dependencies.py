from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import (
    AuthServiceError,
    _faculty_is_approved,
    decode_access_token,
)
from app.db.database import SessionLocal
from app.db.models import (
    AuthAccount,
    FacultyProjectAssignment,
    Project,
    ProjectMember,
)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    id: int
    role: str
    email: str
    student_id: int | None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_token(credentials.credentials)
    except AuthServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        account_id = int(claims["sub"])
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    account = db.get(AuthAccount, account_id)
    if (
        account is None
        or account.role != claims.get("role")
        or not account.email_verified
        or (account.role == "faculty" and not _faculty_is_approved(account))
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not approved to access the application.",
        )
    return Principal(
        id=account.id,
        role=account.role,
        email=account.email,
        student_id=account.student_id,
    )


def require_roles(*roles: str) -> Callable:
    def dependency(account: Principal = Depends(get_current_account)) -> Principal:
        if account.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account does not have permission to perform this action.",
            )
        return account

    return dependency


def ensure_project_access(
    project_id: int,
    account: Principal,
    db: Session,
    *,
    faculty_write: bool = False,
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if account.role == "faculty":
        assigned = db.scalar(
            select(FacultyProjectAssignment.faculty_account_id).where(
                FacultyProjectAssignment.faculty_account_id == account.id,
                FacultyProjectAssignment.project_id == project_id,
            )
        )
        if assigned is None:
            raise HTTPException(status_code=403, detail="Project access is not assigned.")
        return project

    if faculty_write or account.student_id is None:
        raise HTTPException(
            status_code=403,
            detail="Faculty permission is required for this action.",
        )
    membership = db.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.student_id == account.student_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Project access is not authorized.")
    return project


def require_project_access(
    project_id: int,
    account: Principal = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> Principal:
    ensure_project_access(project_id, account, db)
    return account


def require_faculty_project(
    project_id: int,
    account: Principal = Depends(require_roles("faculty")),
    db: Session = Depends(get_db),
) -> Principal:
    ensure_project_access(project_id, account, db, faculty_write=True)
    return account
