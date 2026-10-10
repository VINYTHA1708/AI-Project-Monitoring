import argparse

from sqlalchemy import select

from app.auth.service import _faculty_is_approved, normalize_email
from app.db.database import SessionLocal
from app.db.models import AuthAccount, FacultyProjectAssignment, Project


def assign_faculty(email: str, project_id: int) -> None:
    normalized_email = normalize_email(email)
    with SessionLocal.begin() as db:
        account = db.scalar(
            select(AuthAccount).where(AuthAccount.email == normalized_email)
        )
        if account is None or not _faculty_is_approved(account):
            raise ValueError("An approved, verified faculty account is required.")
        if db.get(Project, project_id) is None:
            raise ValueError("Project not found.")
        existing = db.get(
            FacultyProjectAssignment,
            (account.id, project_id),
        )
        if existing is None:
            db.add(
                FacultyProjectAssignment(
                    faculty_account_id=account.id,
                    project_id=project_id,
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign an allowlisted faculty account to a project."
    )
    parser.add_argument("email", help="Verified faculty email address")
    parser.add_argument("project_id", type=int, help="Existing project ID")
    args = parser.parse_args()
    assign_faculty(args.email, args.project_id)
    print("Faculty project assignment saved.")


if __name__ == "__main__":
    main()
